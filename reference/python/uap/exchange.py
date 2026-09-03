"""Reference exchange (SPEC.md §8-§10).

The exchange runs the auction, signs bundles and decisions, verifies receipts,
and resolves settlement. It is the only role that holds money, which makes it
the only place policy can be enforced against the other four.

Storage here is in-memory and single-process. A production exchange needs a
durable nonce store with a replay window; everything else in this module is the
real logic.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import auction
from .measurement import assess, meets_mrc
from .supply_chain import verify_chain
from .canonical import canonicalize
from .crypto import KeyRing, SigningKey, sign_object, verify_object
from .nonce import derive_local_nonce
from .pacing import allocate

__all__ = ["Exchange", "ReceiptVerdict"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ReceiptVerdict:
    receipt_id: str
    billable: bool
    reason: str
    gross_micros: int = 0
    splits: list = field(default_factory=list)

    def to_json(self) -> dict:
        return {"receipt_id": self.receipt_id, "billable": self.billable,
                "reason": self.reason, "gross_micros": self.gross_micros,
                "splits": self.splits}


class Exchange:
    def __init__(self, entity_id: str, signing_key: SigningKey, *,
                 take_rate_bps: int = 2000, floor_cpm_micros: int = 10_000_000,
                 k_anonymity_floor: int = 500, holdout_rate: float = 0.02):
        self.entity_id = entity_id
        self.key = signing_key
        self.take_rate_bps = take_rate_bps
        self.floor_cpm_micros = floor_cpm_micros
        self.k_anonymity_floor = k_anonymity_floor
        self.holdout_rate = holdout_rate

        self.line_items: list[dict] = []
        self.steward_policies: dict[str, dict] = {}
        self.supply_keys = KeyRing()          # enrolled surface/node keys
        self.enrolled: dict[str, int] = {}    # entity_id -> trust tier

        self._open_nonces: dict[str, dict] = {}   # hosted profile only
        self._bundles: dict[str, dict] = {}       # bundle_id -> issued bundle
        self._kid_entity: dict[str, str] = {}     # signing kid -> supply entity
        self._allocations: dict[tuple, int] = {}  # (bundle_id, entity, line_item) -> slice
        self._spent: dict[str, int] = {}          # line_item_id -> micros settled
        self._spent_nonces: set[str] = set()
        self._delivered: dict[str, int] = {}  # line_item_id -> impressions
        self._delivered_by: dict[str, int] = {}  # entity_id -> verified impressions
        self._events: list[dict] = []
        self._rejections: list[str] = []
        self._verified_count = 0
        self._period_splits: list = []
        self._commitments: dict[str, str] = {}   # request_id -> committed digest
        self._holdout_digests: list[str] = []
        self._served_digests: list[str] = []
        self._receipt_log: list[dict] = []
        self._declarations: dict[str, dict] = {}

    # -- registration ------------------------------------------------------
    def enrol(self, entity_id: str, verifying_key, trust_tier: int) -> None:
        self.supply_keys.add(verifying_key)
        self.enrolled[entity_id] = trust_tier
        self._kid_entity[verifying_key.kid] = entity_id

    def add_line_item(self, item: dict) -> None:
        self.line_items.append(item)

    def register_steward(self, model_id: str, policy: dict) -> None:
        self.steward_policies[model_id] = policy

    def jwks(self) -> dict:
        return {"keys": [self.key.verifying_key.to_jwk()]}

    def sellers_declaration(self) -> dict:
        """The /.well-known/uap-sellers.json document for this exchange."""
        sellers = []
        for entity_id, tier in sorted(self.enrolled.items()):
            sellers.append({
                "seller_id": entity_id,
                "seller_type": "PUBLISHER",
                "name": entity_id,
                "anchor_type": "enrolment" if tier >= 1 else "none",
                "trust_tier": tier,
            })
        return {"version": "1.0", "uap_version": "2026-09-02",
                "contact_email": f"protocol@{self.entity_id}", "sellers": sellers}

    def record_event(self, event: dict) -> None:
        self._events.append(event)

    def settlement_record(self, period: str) -> dict:
        """Verified and rejected counts with itemised reasons.

        Reporting a rejection rate without reasons is how the open web lost
        publisher trust, so the reasons are part of the response, not support.
        """
        reasons: dict[str, int] = {}
        for reason in self._rejections:
            key = reason.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
        return {"period": period,
                "verified_receipts": self._verified_count,
                "rejected_receipts": len(self._rejections),
                "rejection_reasons": reasons,
                "splits": self._period_splits,
                "mandate": None}

    # -- manifest ----------------------------------------------------------
    def manifest(self, base_url: str) -> dict:
        return {
            "uap_version": "2026-09-02",
            "entity": {"id": self.entity_id, "role": ["exchange"]},
            "profiles": ["uap.core", "uap.decision.local", "uap.decision.hosted",
                         "uap.measure", "uap.settle", "uap.supplychain"],
            "services": [{"name": "dev.uap.ads", "version": "2026-09-02",
                          "base_url": base_url, "transport": "rest",
                          "capabilities": [
                              {"name": "dev.uap.ads.decision", "version": "2026-09-02"},
                              {"name": "dev.uap.ads.bundle", "version": "2026-09-02"},
                              {"name": "dev.uap.ads.receipt", "version": "2026-09-02"},
                          ]}],
            "auction": {"mechanisms": ["uap.auction.second_price"],
                        "currencies": ["USD"],
                        "default_floor_cpm_micros": self.floor_cpm_micros},
            "privacy": {"max_context_signal_class": "coarse",
                        "k_anonymity_floor": self.k_anonymity_floor,
                        "retention_days": 30},
            "keys": base_url.rsplit("/uap", 1)[0] + "/.well-known/jwks.json",
        }

    # -- Profile L: bundle issuance ---------------------------------------
    def issue_bundle(self, *, formats=None, locales=None, ttl_hours: int = 24) -> dict:
        """Return a signed CampaignBundle for local decisioning.

        Bundle variants are coarse by construction. A bundle personalised to one
        node would let the exchange infer that node's audience from which bundle
        it requested, which is the side channel §8.2 exists to close.
        """
        items = [i for i in self.line_items
                 if not formats or any(c.get("format") in formats
                                       for c in (i.get("creatives") or [{}]))]
        bundle = {
            "bundle_id": "bn_" + secrets.token_hex(6),
            "issued_at": _iso(_now()),
            "expires_at": _iso(_now() + timedelta(hours=ttl_hours)),
            "taxonomy_version": "uap.intent/1.0",
            "floor_cpm_micros": self.floor_cpm_micros,
            "line_items": items,
        }
        signed = sign_object(bundle, self.key, "bundle", created=_iso(_now()))
        self._bundles[bundle["bundle_id"]] = signed
        return signed

    def issue_allocation(self, bundle_id: str, entity_id: str, *,
                         period_fraction: float = 1 / 24) -> dict:
        """Sign a per-node allocation against an issued bundle.

        Slices are computed so that, summed across every enrolled node, they
        cannot exceed each line item's remaining budget. A node serving inside
        its slice is therefore always paid; over-allocation is the exchange's
        error and the exchange bears it. The bundle body is unchanged per node.
        """
        bundle = self._bundles[bundle_id]
        history = {e: self._delivered_by.get(e, 0) for e in self.enrolled}
        slices = {}
        for item in bundle.get("line_items") or []:
            lid = item["line_item_id"]
            budget = (item.get("pacing") or {}).get("budget_micros")
            if budget is None:
                continue                              # uncapped line item: no slice needed
            remaining = max(0, budget - self._spent.get(lid, 0))
            price = item["pricing"].get("bid_cpm_micros") or self.floor_cpm_micros
            alloc = allocate(item, history or {entity_id: 0}, remaining_budget_micros=remaining,
                             expected_price_cpm_micros=price, period_fraction=period_fraction)
            for e, n in alloc.slices.items():
                self._allocations[(bundle_id, e, lid)] = n
            slices[lid] = alloc.slices.get(entity_id, 0)
        obj = {"bundle_id": bundle_id, "entity_id": entity_id,
               "issued_at": _iso(_now()), "expires_at": bundle["expires_at"], "slices": slices}
        return sign_object(obj, self.key, "bundle", created=_iso(_now()))

    # -- Profile H: hosted decisioning ------------------------------------
    def decide(self, ad_request: dict) -> dict | None:
        """Run a hosted auction. Returns a signed Decision, or None for no-fill.

        The request carries the node's commitment to the organic answer. It is
        recorded here, before a winner exists, which is what makes the ordering
        provable: an answer matching this digest could not have depended on the
        auction outcome.
        """
        request_id = ad_request.get("id") or ad_request.get("request_id") or ""
        integrity = ad_request.get("integrity") or {}
        committed = integrity.get("organic_answer_digest")
        if not committed:
            raise ValueError(
                "AdRequest must carry integrity.organic_answer_digest. "
                "Without a commitment made before selection there is nothing to "
                "check the rendered answer against, and I2 becomes an assertion.")
        self._commitments[request_id] = committed

        # A holdout runs the identical path and serves nothing. Divergence
        # between served and holdout answer distributions is the only evidence
        # of decode influence that no per-turn check can produce.
        if self._is_holdout(request_id):
            self._holdout_digests.append(committed)
            return None
        self._served_digests.append(committed)

        signal = ad_request.get("context") or {}
        if (signal.get("safety") or {}).get("sensitive_category"):
            return None  # §6.7: a sensitive turn produces no AdRequest at all

        supply = ad_request.get("supply") or {}
        steward = self.steward_policies.get((supply.get("model") or {}).get("id", ""))

        placements = []
        for placement in ad_request.get("placements") or []:
            result = auction.run(
                self.line_items, signal, placement,
                policy=ad_request.get("policy") or {},
                steward_policy=steward,
                floor_cpm_micros=self.floor_cpm_micros,
                pacing_state=self._delivered,
            )
            if not result.winner:
                continue
            nonce = "n_" + secrets.token_hex(16)
            creative = (result.winner.get("creatives") or [{}])[0]
            self._open_nonces[nonce] = {
                "committed_digest": committed,
                "line_item_id": result.winner["line_item_id"],
                "creative_digest": creative.get("content_digest"),
                "price_micros": result.clearing_price_micros,
                "supply_entity": supply.get("entity_id"),
                "issued_at": time.time(),
                "trace": result.trace_json(),
            }
            placements.append({
                "placement_id": placement.get("placement_id"),
                "creative": creative,
                "clearing": {"price_cpm_micros": result.clearing_price_micros,
                             "currency": "USD", "mechanism": result.mechanism},
                "nonce": nonce,
                "click_id": "ck_" + secrets.token_hex(8),
            })

        if not placements:
            return None
        decision = {
            "decision_id": "dc_" + secrets.token_hex(10),
            "request_id": ad_request.get("request_id"),
            "issued_at": _iso(_now()),
            "expires_at": _iso(_now() + timedelta(minutes=5)),
            "placements": placements,
        }
        return sign_object(decision, self.key, "decision", created=_iso(_now()))

    # -- Profile L: reconstruct a locally-derived decision ------------------
    def _resolve_local(self, receipt: dict, entity_id: str) -> tuple[dict | None, str]:
        """Rebuild what a Profile L receipt claims, from the bundle we signed.

        Nothing here trusts the node. The bundle is ours, the nonce is
        recomputed, the pacing allocation is ours, and the clearing price is
        derived from the reported trace rather than read from the receipt.
        """
        ld = receipt.get("local_decision") or {}
        bundle_id = ld.get("bundle_id")
        line_item_id = ld.get("line_item_id")
        index = ld.get("impression_index")
        if not (bundle_id and line_item_id and isinstance(index, int)):
            return None, "local_decision is missing or malformed"

        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            return None, f"unknown bundle {bundle_id}"
        if receipt.get("rendered_at", "") > bundle.get("expires_at", ""):
            return None, "UAP_BUNDLE_EXPIRED: rendered after the bundle expired"

        item = next((i for i in bundle["line_items"]
                     if i.get("line_item_id") == line_item_id), None)
        if item is None:
            return None, f"line item {line_item_id} is not in bundle {bundle_id}"

        expected = derive_local_nonce(bundle_id, entity_id, line_item_id, index)
        if receipt.get("nonce") != expected:
            return None, "nonce does not derive from the declared local_decision"

        share = self._allocations.get((bundle_id, entity_id, line_item_id))
        if share is None:
            share = (item.get("pacing") or {}).get("node_share_impressions")
        if share is not None and index >= share:
            return None, f"UAP_PACING_EXCEEDED: index {index} exceeds allocation {share}"

        trace = receipt.get("auction_trace") or []
        won = [t for t in trace if t.get("outcome") == "won"]
        if len(won) != 1 or won[0].get("line_item_id") != line_item_id:
            return None, "auction_trace does not name this line item as the winner"

        # Derive the clearing price ourselves. Second price is the highest
        # losing eCPM, floored, plus one micro.
        floor = bundle.get("floor_cpm_micros", 0)
        lost = [t.get("ecpm_micros", 0) for t in trace if t.get("outcome") == "lost"]
        price = max(max(lost, default=0), floor) + 1

        creative = (item.get("creatives") or [{}])[0]
        return {"line_item_id": line_item_id,
                "creative_digest": creative.get("content_digest"),
                "price_micros": price, "supply_entity": entity_id,
                "issued_at": time.time(), "trace": trace}, "ok"

    def _is_holdout(self, request_id: str) -> bool:
        """Deterministic holdout selection, so a node cannot detect or avoid it.

        Keyed on the request id rather than sampled randomly: the decision is
        reproducible at audit time, and a node that learns the rate still cannot
        predict which of its requests will be held out.
        """
        if self.holdout_rate <= 0:
            return False
        digest = hashlib.sha256((self.entity_id + "|" + request_id).encode()).digest()
        return (int.from_bytes(digest[:4], "big") / 0xFFFFFFFF) < self.holdout_rate

    def register_declaration(self, asi: str, declaration: dict) -> None:
        """Cache another system's uap-sellers.json for chain verification."""
        self._declarations[asi] = declaration

    def check_supply_chain(self, ad_request: dict):
        """Verify the declared chain before bidding. Buyers require this."""
        chain = (ad_request.get("source") or {}).get("supply_chain")
        declarations = dict(self._declarations)
        declarations.setdefault(self.entity_id, self.sellers_declaration())
        return verify_chain(chain or {}, declarations)

    def quality_report(self):
        """Measurement quality across verified receipts, in MRC vocabulary."""
        return assess(self._receipt_log)

    def holdout_report(self) -> dict:
        """Counts for the served and held-out arms of the integrity experiment."""
        return {"served": len(self._served_digests),
                "holdout": len(self._holdout_digests),
                "holdout_rate_observed": (
                    len(self._holdout_digests)
                    / max(1, len(self._served_digests) + len(self._holdout_digests))),
                "note": ("Answer digests from both arms. Systematic divergence in "
                         "downstream answer distributions is evidence of decode "
                         "influence; a per-turn check cannot detect it.")}

    # -- receipts ----------------------------------------------------------
    def verify_receipt(self, receipt: dict) -> ReceiptVerdict:
        """Apply every settlement-time check. Only verified receipts are billed."""
        rid = receipt.get("receipt_id", "?")

        def reject(why: str) -> ReceiptVerdict:
            self._rejections.append(why)
            return ReceiptVerdict(rid, False, why)

        ok, reason = verify_object(receipt, self.supply_keys, "receipt")
        if not ok:
            return reject(f"signature: {reason}")

        nonce = receipt.get("nonce")
        if nonce in self._spent_nonces:
            return reject("UAP_NONCE_SPENT: replay")

        if "local_decision" in receipt:
            # The entity is resolved from the signing key, never from a field
            # the node controls. A node cannot derive a valid nonce for supply
            # it is not enrolled as.
            kid = (receipt.get("signature") or {}).get("kid", "")
            entity_id = self._kid_entity.get(kid)
            if entity_id is None:
                return reject("UAP_KEY_NOT_ENROLLED: signing key maps to no entity")
            open_nonce, why = self._resolve_local(receipt, entity_id)
            if open_nonce is None:
                return reject(why)
        else:
            open_nonce = self._open_nonces.get(nonce)
            if open_nonce is None:
                return reject("UAP_NONCE_SPENT: unknown or expired nonce")

        if receipt.get("creative_digest") != open_nonce["creative_digest"]:
            return reject("creative_digest does not match what was issued")

        integrity = receipt.get("integrity") or {}
        for field_name in ("no_decode_influence", "ad_excluded_from_context", "disclosure_rendered"):
            if integrity.get(field_name) is not True:
                return reject(f"integrity: {field_name} not asserted")
        shown = integrity.get("organic_answer_digest", "")
        if not shown.startswith("sha256:"):
            return reject("integrity: missing organic_answer_digest")
        committed = open_nonce.get("committed_digest")
        if committed and shown != committed:
            return reject("integrity: the answer rendered does not match the digest "
                          "committed before selection ran")

        view = receipt.get("viewability") or {}
        if not view.get("rendered"):
            return reject("not rendered")
        # A viewable claim is priced, so it is checked against the MRC threshold
        # it names rather than accepted as asserted.
        if view.get("viewable"):
            ok_mrc, why_mrc = meets_mrc(view)
            if not ok_mrc:
                return reject(f"viewability: {why_mrc}")
        tier = receipt.get("trust_tier", 0)
        if tier == 0:
            return reject("UAP_TIER_INSUFFICIENT: tier 0 is not CPM-eligible")
        if view.get("standard") == "delivered_only" and view.get("viewable"):
            return reject("delivered_only surface asserted viewability")

        trace = receipt.get("auction_trace")
        if trace is not None and trace != open_nonce["trace"]:
            return reject("auction_trace does not replay against the issued bundle")

        self._spent_nonces.add(nonce)
        self._open_nonces.pop(nonce, None)
        self._receipt_log.append(receipt)
        self._delivered[open_nonce["line_item_id"]] = self._delivered.get(open_nonce["line_item_id"], 0) + 1

        gross = open_nonce["price_micros"] // 1000  # CPM covers one thousand
        self._spent[open_nonce["line_item_id"]] = self._spent.get(open_nonce["line_item_id"], 0) + gross
        self._delivered_by[open_nonce["supply_entity"]] = self._delivered_by.get(open_nonce["supply_entity"], 0) + 1
        splits = self.settle(gross, open_nonce["supply_entity"])
        self._verified_count += 1
        self._period_splits = splits
        return ReceiptVerdict(rid, True, "verified", gross, splits)

    # -- settlement --------------------------------------------------------
    def settle(self, gross_micros: int, supply_entity: str,
               steward_id: str | None = None, steward_bps: int = 1500) -> list:
        """Resolve the revenue split. Basis points sum to exactly 10000."""
        exchange_bps = self.take_rate_bps
        steward_bps = steward_bps if steward_id else 0
        node_bps = 10000 - exchange_bps - steward_bps
        parties = [("serving_node", supply_entity, node_bps),
                   ("exchange", self.entity_id, exchange_bps)]
        if steward_id:
            parties.insert(1, ("model_steward", steward_id, steward_bps))

        # Largest-remainder allocation so the parts sum to the whole exactly.
        raw = [(gross_micros * bps) / 10000 for _, _, bps in parties]
        floors = [int(r) for r in raw]
        shortfall = gross_micros - sum(floors)
        order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
        for i in order[:shortfall]:
            floors[i] += 1

        return [{"party": p, "entity_id": e, "bps": b, "amount_micros": a}
                for (p, e, b), a in zip(parties, floors)]
