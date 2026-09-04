"""Client for the buy side: what an advertiser, agency or DSP calls.

    from uap import DemandClient

    dsp = DemandClient("https://uax.example.com", advertiser_id="brand.acme.example",
                       agent="brand.acme.example; role=advertiser; v=2026-09-02")

    campaign = dsp.create_campaign(name="Q4 Japan", objective="clicks",
                                   budget_micros=5_000_000_000, currency="USD",
                                   spend_mandate="ap2:intent:...")
    item = dsp.create_line_item(campaign["campaign_id"], targeting={...},
                                pricing={"model": "cpc", "currency": "USD", "bid_cpc_micros": 900_000},
                                creative={...})
    print(dsp.forecast(targeting={...}, pricing={...}))

Thin by design. Every method is one HTTP call to the demand service; the
shapes are the schemas under source/schemas/demand/.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

__all__ = ["DemandClient", "DemandError"]


class DemandError(RuntimeError):
    def __init__(self, status: int, problem: dict):
        super().__init__(f"{status} {problem.get('code', '')}: {problem.get('detail') or problem.get('title', '')}")
        self.status = status
        self.problem = problem


class DemandClient:
    def __init__(self, base_url: str, *, advertiser_id: str, agent: str | None = None,
                 token: str | None = None, timeout_s: float = 10.0):
        self.base = base_url.rstrip("/")
        self.advertiser_id = advertiser_id
        self.agent = agent or f"{advertiser_id}; role=advertiser; v=2026-09-02"
        self.token = token
        self.timeout_s = timeout_s
        self._seq = 0

    # -- transport -------------------------------------------------------------
    def _call(self, method: str, path: str, body=None):
        self._seq += 1
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("UAP-Agent", self.agent)
        req.add_header("UAP-Request-Id", f"{int(time.time() * 1000):x}-{self._seq:04x}")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.add_header("Idempotency-Key", f"{int(time.time() * 1e6):x}-{self._seq:04x}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            try:
                problem = json.loads(e.read() or b"{}")
            except json.JSONDecodeError:
                problem = {}
            raise DemandError(e.code, problem) from None

    # -- campaigns -------------------------------------------------------------
    def create_campaign(self, *, name: str, objective: str, budget_micros: int, currency: str,
                        spend_mandate: str, campaign_id: str | None = None,
                        daily_micros: int | None = None, flight: dict | None = None,
                        supply: dict | None = None, labels: dict | None = None) -> dict:
        body = {"name": name, "objective": objective, "status": "active",
                "budget": {"total_micros": budget_micros, "currency": currency,
                           "spend_mandate": spend_mandate,
                           **({"daily_micros": daily_micros} if daily_micros else {})}}
        if campaign_id: body["campaign_id"] = campaign_id
        if flight: body["flight"] = flight
        if supply: body["supply"] = supply
        if labels: body["labels"] = labels
        return self._call("POST", f"/uap/v1/advertisers/{self.advertiser_id}/campaigns", body)

    def list_campaigns(self) -> list:
        return (self._call("GET", f"/uap/v1/advertisers/{self.advertiser_id}/campaigns") or {}).get("items", [])

    def get_campaign(self, campaign_id: str) -> dict:
        return self._call("GET", f"/uap/v1/campaigns/{campaign_id}")

    def pause(self, campaign_id: str) -> dict:
        return self._call("POST", f"/uap/v1/campaigns/{campaign_id}:pause", {})

    def resume(self, campaign_id: str) -> dict:
        return self._call("POST", f"/uap/v1/campaigns/{campaign_id}:resume", {})

    # -- line items and creatives ----------------------------------------------
    def create_line_item(self, campaign_id: str, *, targeting: dict, pricing: dict,
                         creative: dict, display_name: str | None = None,
                         line_item_id: str | None = None, pacing: dict | None = None,
                         frequency_cap: dict | None = None, categories: list | None = None,
                         brand_safety: dict | None = None) -> dict:
        body = {"advertiser": {"id": self.advertiser_id,
                               "display_name": display_name or self.advertiser_id},
                "targeting": targeting, "pricing": pricing, "creatives": [creative]}
        for k, v in (("line_item_id", line_item_id), ("pacing", pacing),
                     ("frequency_cap", frequency_cap), ("categories", categories),
                     ("brand_safety", brand_safety)):
            if v is not None:
                body[k] = v
        return self._call("POST", f"/uap/v1/campaigns/{campaign_id}/line-items", body)

    def submit_creative(self, line_item_id: str, creative: dict) -> dict:
        """Returns the review status; rejected creatives list their reasons."""
        return self._call("POST", f"/uap/v1/line-items/{line_item_id}/creatives", creative)

    def review_status(self, creative_id: str) -> dict:
        return self._call("GET", f"/uap/v1/creatives/{creative_id}/review")

    # -- planning and measurement ----------------------------------------------
    def forecast(self, *, targeting: dict, pricing: dict, flight: dict | None = None,
                 supply: dict | None = None) -> dict:
        body = {"targeting": targeting, "pricing": pricing, "flight": flight or {}}
        if supply: body["supply"] = supply
        return self._call("POST", "/uap/v1/forecast", body)

    def report_conversions(self, events: list) -> dict:
        return self._call("POST", "/uap/v1/conversions", {"events": events})

    def report(self, *, start: str, end: str, metrics: list, dimensions: list | None = None,
               campaign_ids: list | None = None, granularity: str = "day") -> dict:
        body = {"scope": {"advertiser_id": self.advertiser_id,
                          **({"campaign_ids": campaign_ids} if campaign_ids else {})},
                "period": {"start": start, "end": end}, "granularity": granularity,
                "dimensions": dimensions or [], "metrics": metrics}
        return self._call("POST", "/uap/v1/reports", body)
