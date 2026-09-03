"""Buy side of the reference exchange: campaigns, review, forecast, reporting.

What an advertiser or agency integrates against. In-memory like the rest of the
reference exchange; the logic is the real logic, the storage is not.

Four rules that a conventional platform API does not have, each enforced here:

  no audience object     targeting is a predicate over ContextSignal; there is
                         no user list to upload and no identifier to key on
  review before serving  a creative reaches an auction only after its URLs
                         resolve to verified domains and its text has been
                         scanned for instruction-shaped content
  conversions by source  a serving node cannot report a conversion; only the
                         advertiser or a payment mandate can
  aggregate reporting    a closed dimension set, at most four, cells under the
                         k floor suppressed, noise on intent breakdowns
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from . import predicate
from .canonical import canonicalize

__all__ = ["BuySide", "CreativeReviewError"]

REJECTION = {
    "url_not_verified_domain", "redirect_chain_changed", "instruction_shaped_text",
    "markup_in_field", "blocked_category", "disclosure_missing",
    "asset_digest_mismatch", "length_exceeded",
}

# Text that reads as an instruction to a model rather than as an advertisement.
# Reviewed at submission because a node MUST NOT rely on this scan (§13); the
# render path escapes everything regardless. This catches the obvious cases so
# they never enter a bundle at all.
_INSTRUCTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above)|you are (now |an? )|system ?:|assistant ?:"
    r"|<\|[a-z_]+\|>|\[INST\]|###\s*(instruction|system)|do not (tell|mention)"
    r"|respond (only )?with|from now on)", re.I)
_MARKUP = re.compile(r"<[a-zA-Z/!][^>]*>|\{\{|\}\}|\$\{")

REPORT_DIMENSIONS = {"campaign", "line_item", "creative", "format", "position",
                     "intent_depth1", "intent_depth2", "locale", "country",
                     "trust_tier", "profile", "model_id", "seller_id", "label"}
INTENT_DIMENSIONS = {"intent_depth1", "intent_depth2"}
MIN_CELL_EVENTS = 50
DP_EPSILON = 1.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CreativeReviewError(ValueError):
    def __init__(self, reasons: list[str]):
        super().__init__(", ".join(reasons))
        self.reasons = reasons


class BuySide:
    def __init__(self, exchange, *, k_anonymity_floor: int = 500, rng: random.Random | None = None):
        self.exchange = exchange
        self.k_floor = k_anonymity_floor
        self.rng = rng or random.Random(0)      # seeded so reports are reproducible in tests

        self.campaigns: dict[str, dict] = {}
        self.line_items: dict[str, dict] = {}
        self.creatives: dict[str, dict] = {}
        self.brands: dict[str, dict] = {}          # advertiser_id -> uap-brand manifest
        self.conversions: dict[str, dict] = {}     # event_id -> event
        self.clicks: dict[str, dict] = {}          # click_id -> {line_item_id, at}
        self.traffic: list[dict] = []              # sampled ContextSignals, for forecasting
        self.daily_turns: int = 0

    # -- advertisers ---------------------------------------------------------
    def register_brand(self, advertiser_id: str, manifest: dict) -> None:
        """Cache an advertiser's /.well-known/uap-brand; review checks URLs against it."""
        self.brands[advertiser_id] = manifest

    # -- campaigns -----------------------------------------------------------
    def create_campaign(self, campaign: dict) -> dict:
        cid = campaign.get("campaign_id") or "cmp_" + secrets.token_hex(6)
        if not campaign.get("budget", {}).get("spend_mandate"):
            raise ValueError("UAP_MANDATE_REQUIRED: a campaign needs an AP2 spend mandate before it can run")
        rec = {**campaign, "campaign_id": cid, "status": campaign.get("status", "draft"),
               "created_at": _iso(_now()), "updated_at": _iso(_now()), "line_items": []}
        self.campaigns[cid] = rec
        for li in campaign.get("line_items") or []:
            self.create_line_item(cid, li)
        return rec

    def set_campaign_status(self, cid: str, status: str) -> dict:
        c = self.campaigns[cid]
        if status == "active" and c["status"] == "draft" and not any(
                self.line_items[l]["status"] == "active" for l in c["line_items"]):
            raise ValueError("UAP_NO_SERVABLE_LINE_ITEMS: activate a line item with an approved creative first")
        c["status"] = status
        c["updated_at"] = _iso(_now())
        self._sync_exchange()
        return c

    # -- line items ----------------------------------------------------------
    def create_line_item(self, cid: str, item: dict) -> dict:
        if cid not in self.campaigns:
            raise KeyError(cid)
        lid = item.get("line_item_id") or "li_" + secrets.token_hex(6)
        if item.get("targeting") is not None:
            predicate.validate(item["targeting"])          # Appendix A bounds, at write time
        rec = {**item, "line_item_id": lid, "campaign_id": cid, "status": "draft", "creatives": []}
        self.line_items[lid] = rec
        self.campaigns[cid]["line_items"].append(lid)
        for cr in item.get("creatives") or []:
            self.submit_creative(lid, cr)
        return rec

    # -- creative review -----------------------------------------------------
    def review_creative(self, advertiser_id: str, creative: dict) -> list[str]:
        """Return rejection reasons; empty means approved."""
        reasons = []
        content = creative.get("content") or {}
        brand = self.brands.get(advertiser_id) or {}
        verified = set(brand.get("verified_domains") or [])

        for action in content.get("actions") or []:
            url = action.get("url") or ""
            host = urlparse(url).hostname or ""
            if not url.startswith("https://") or not any(
                    host == d or host.endswith("." + d) for d in verified):
                reasons.append("url_not_verified_domain")
                break

        for field in ("headline", "body", "brand_name"):
            text = content.get(field) or ""
            if _INSTRUCTION.search(text):
                reasons.append("instruction_shaped_text"); break
        for field in ("headline", "body", "brand_name"):
            if _MARKUP.search(content.get(field) or ""):
                reasons.append("markup_in_field"); break

        if not (creative.get("disclosure") or {}).get("advertiser_name"):
            reasons.append("disclosure_missing")
        if len(content.get("headline") or "") > 120 or len(content.get("body") or "") > 280:
            reasons.append("length_exceeded")

        return sorted(set(reasons))

    def submit_creative(self, lid: str, creative: dict) -> dict:
        li = self.line_items[lid]
        adv = (li.get("advertiser") or {}).get("id", "")
        reasons = self.review_creative(adv, creative)
        digest = "sha256:" + hashlib.sha256(canonicalize(creative.get("content") or {})).hexdigest()
        rec = {**creative, "content_digest": digest,
               "review": {"status": "rejected" if reasons else "approved",
                          "reviewer": self.exchange.entity_id,
                          "policy_version": "2026-08-01",
                          "rejection_reasons": reasons}}
        self.creatives[rec["creative_id"]] = rec
        li["creatives"] = [c for c in li["creatives"] if c["creative_id"] != rec["creative_id"]] + [rec]
        li["status"] = "active" if not reasons else "rejected"
        self._sync_exchange()
        return rec

    def _sync_exchange(self) -> None:
        """Only active line items of active campaigns reach bundles and auctions."""
        self.exchange.line_items = [
            li for li in self.line_items.values()
            if li["status"] == "active"
            and self.campaigns[li["campaign_id"]]["status"] == "active"
            and any(c["review"]["status"] == "approved" for c in li["creatives"])
        ]

    # -- forecasting ---------------------------------------------------------
    def record_traffic(self, signal: dict) -> None:
        """Sample a bounded signal for forecasting. Never the conversation."""
        self.traffic.append(signal)

    def forecast(self, request: dict) -> dict:
        matcher = predicate.compile_predicate(request["targeting"])
        prepared = [predicate.prepare(s) for s in self.traffic]
        matched = [s for s in prepared if matcher(s)]
        share = len(matched) / len(prepared) if prepared else 0.0
        per_day = int(self.daily_turns * share)

        def rng(n): return {"low": int(n * 0.8), "high": int(n * 1.2)}

        # Cohort estimate: distinct (intent-set, locale, country) combinations
        # among matched traffic. Breakdowns below the k floor are suppressed.
        cohorts = {(tuple(sorted(i["id"] for i in s.get("intents") or [])),
                    s.get("locale"), (s.get("geo") or {}).get("value")) for s in matched}
        suppressed = []
        by_tier = {}
        for tier in ("0", "1", "2"):
            n = sum(1 for s in matched if str(s.get("_trust_tier", 1)) == tier)
            if n and n * (self.daily_turns / max(1, len(prepared))) >= self.k_floor:
                by_tier[tier] = rng(int(per_day * n / max(1, len(matched))))
            elif n:
                suppressed.append(f"by_trust_tier.{tier}")

        pricing = request.get("pricing") or {}
        bid = pricing.get("bid_cpm_micros") or 0
        floor = self.exchange.floor_cpm_micros
        competing = [li["pricing"].get("bid_cpm_micros", 0) for li in self.exchange.line_items
                     if li["pricing"].get("model") == "cpm"]
        beaten = sum(1 for b in competing if bid > b)
        win_rate = 0.0 if bid < floor else (beaten + 1) / (len(competing) + 1)
        clearing = max(floor, max([b for b in competing if b < bid], default=floor))
        imps = int(per_day * win_rate)
        return {
            "forecast_id": "fc_" + secrets.token_hex(6),
            "generated_at": _iso(_now()),
            "valid_until": _iso(_now() + timedelta(hours=12)),
            "matched": {"impressions_per_day": rng(per_day),
                        "unique_cohort_estimate": len(cohorts),
                        "by_trust_tier": by_tier},
            "estimate": {"win_rate": round(win_rate, 2),
                         "impressions": rng(imps),
                         "clicks": rng(int(imps * 0.02)),
                         "spend_micros": rng(int(imps * clearing / 1000)),
                         "clearing_cpm_micros": {"low": int(clearing * 0.9), "high": int(clearing * 1.1)},
                         "bid_to_win_cpm_micros": int(max(competing, default=floor) * 1.05)},
            "suppressed": suppressed,
        }

    # -- conversions ---------------------------------------------------------
    def record_click(self, click_id: str, line_item_id: str) -> None:
        self.clicks[click_id] = {"line_item_id": line_item_id, "at": _now()}

    def report_conversion(self, event: dict, *, caller_role: str) -> dict:
        eid = event.get("event_id", "")
        if caller_role == "serving_node" or (event.get("source") or {}).get("kind") not in (
                "advertiser_server", "ap2_payment_mandate", "ucp_checkout"):
            return {"event_id": eid, "accepted": False, "reason": "unenrolled_source"}
        if eid in self.conversions:
            return {"event_id": eid, "accepted": False, "reason": "duplicate"}
        click = self.clicks.get(event.get("click_id", ""))
        if click is None:
            return {"event_id": eid, "accepted": False, "reason": "unknown_click_id"}
        li = self.line_items.get(click["line_item_id"]) or {}
        window_h = ((li.get("attribution") or {}).get("conversion_window_hours")) or 168
        if _now() - click["at"] > timedelta(hours=window_h):
            return {"event_id": eid, "accepted": False, "reason": "outside_window"}
        self.conversions[eid] = {**event, "line_item_id": click["line_item_id"]}
        return {"event_id": eid, "accepted": True, "reason": "ok"}

    # -- reporting -----------------------------------------------------------
    def run_report(self, request: dict) -> dict:
        dims = list(request.get("dimensions") or [])
        if len(dims) > 4:
            raise ValueError("UAP_REPORT_DIMENSIONS: at most four dimensions")
        unknown = [d for d in dims if d not in REPORT_DIMENSIONS]
        if unknown:
            raise ValueError(f"UAP_REPORT_DIMENSIONS: not reportable: {unknown}")

        cells: dict[tuple, dict] = {}
        for r in self.exchange._receipt_log:
            key = tuple(self._dim_value(d, r) for d in dims)
            c = cells.setdefault(key, {"impressions": 0, "viewable_impressions": 0,
                                       "clicks": 0, "conversions": 0, "spend_micros": 0})
            c["impressions"] += 1
            if (r.get("viewability") or {}).get("viewable"):
                c["viewable_impressions"] += 1
            c["spend_micros"] += r.get("_gross_micros", 0)
        for cv in self.conversions.values():
            key = tuple(self._dim_value(d, {"line_item_id": cv["line_item_id"]}) for d in dims)
            if key in cells:
                cells[key]["conversions"] += 1

        noisy = bool(set(dims) & INTENT_DIMENSIONS)
        rows, suppressed = [], 0
        for key, c in cells.items():
            if c["impressions"] < MIN_CELL_EVENTS:
                suppressed += 1
                continue
            vals = dict(c)
            if noisy:
                for m in ("impressions", "clicks", "conversions"):
                    vals[m] = max(0, int(vals[m] + self._laplace(1.0 / DP_EPSILON)))
            vals["ecpm_micros"] = int(vals["spend_micros"] * 1000 / max(1, vals["impressions"]))
            vals["ctr"] = round(vals["clicks"] / max(1, vals["impressions"]), 4)
            rows.append({"period": f"{request['period']['start']}/{request['period']['end']}",
                         "keys": dict(zip(dims, key)),
                         "values": {m: vals[m] for m in request["metrics"] if m in vals}})
        return {"report_id": "rp_" + secrets.token_hex(6),
                "generated_at": _iso(_now()),
                "privacy": {"k_anonymity_floor": self.k_floor, "min_cell_events": MIN_CELL_EVENTS,
                            **({"dp_epsilon": DP_EPSILON} if noisy else {}),
                            "suppressed_cells": suppressed},
                "rows": rows}

    def _dim_value(self, dim: str, receipt: dict) -> str:
        lid = receipt.get("line_item_id") or (receipt.get("local_decision") or {}).get("line_item_id", "")
        li = self.line_items.get(lid) or {}
        if dim == "line_item":
            return lid
        if dim == "campaign":
            return li.get("campaign_id", "")
        if dim == "creative":
            return receipt.get("creative_digest", "")[:16]
        if dim == "trust_tier":
            return str(receipt.get("trust_tier", ""))
        if dim == "label":
            return ",".join(f"{k}={v}" for k, v in sorted(
                (self.campaigns.get(li.get("campaign_id", ""), {}).get("labels") or {}).items()))
        return str(receipt.get("_" + dim, "") or "")

    def _laplace(self, scale: float) -> float:
        u = self.rng.random() - 0.5
        return -scale * math.copysign(1, u) * math.log(1 - 2 * abs(u))
