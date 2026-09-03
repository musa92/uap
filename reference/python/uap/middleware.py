"""Drop-in monetisation for any OpenAI-compatible inference server.

vLLM, SGLang, Ollama, llama.cpp, TGI, LM Studio and every hosted provider expose
the same /v1/chat/completions contract, so one wrapper covers all of them.

    from uap.middleware import UAPMiddleware

    ads = UAPMiddleware(node, surface, exchange_url="https://uax.example.com")
    response = ads.complete(upstream, request)   # upstream is your own client

The ordering is enforced here rather than left to the caller: the upstream call
completes before selection begins, and selection has no way to reach it.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .crypto import verify_object
from .integrity import SEPARATOR
from .node import KeywordClassifier, Node, Surface

__all__ = ["UAPMiddleware", "ExchangeClient"]


class ExchangeClient:
    """Minimal HTTP client for the supply service."""

    def __init__(self, base_url: str, agent: str, timeout_s: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.agent = agent
        self.timeout_s = timeout_s
        self._seq = 0

    def _call(self, method: str, path: str, body: Any = None, timeout: float | None = None):
        self._seq += 1
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("UAP-Agent", self.agent)
        req.add_header("UAP-Request-Id", f"{int(time.time()*1000):x}-{self._seq:04x}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.add_header("Idempotency-Key", f"{int(time.time()*1e6):x}-{self._seq:04x}")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout_s) as resp:
                if resp.status == 204:
                    return None
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{exc.code} {exc.read()[:200]!r}") from exc

    def manifest(self):
        return self._call("GET", "/.well-known/uap")

    def jwks(self):
        return self._call("GET", "/.well-known/jwks.json")

    def bundle(self, formats: str = "", locales: str = ""):
        q = []
        if formats:
            q.append(f"formats={formats}")
        if locales:
            q.append(f"locales={locales}")
        return self._call("GET", "/uap/v1/bundles" + ("?" + "&".join(q) if q else ""))

    def decide(self, ad_request: dict, timeout_ms: int = 80):
        return self._call("POST", "/uap/v1/decisions", ad_request, timeout=timeout_ms / 1000)

    def allocation(self, bundle_id: str):
        return self._call("GET", "/uap/v1/allocations?bundle_id=" + bundle_id)

    def receipts(self, receipts: list):
        return self._call("POST", "/uap/v1/receipts:batch", {"receipts": receipts})

    def event(self, event: dict):
        return self._call("POST", "/uap/v1/events", event)


class UAPMiddleware:
    """Wraps a chat-completions call and appends a disclosed sponsored block.

    Fails open toward the user and closed toward the advertiser: any error in the
    ad path returns the unmodified completion. A monetisation bug must never cost
    the operator an answer.
    """

    DEFAULT_PLACEMENT = {
        "placement_id": "pl_post_answer",
        "position": "post_answer",
        "format": "sponsored_card",
        "surface": {"type": "chat", "renderer": "markdown", "client": "api"},
        "disclosure": {"required": True, "label": "Sponsored"},
        "floor_cpm_micros": 10_000_000,
        "max_ads": 1,
    }

    def __init__(self, node: Node, surface: Surface, client: ExchangeClient | None = None,
                 *, placement: dict | None = None, classifier=None,
                 batch_seconds: int = 60, enabled: Callable[[dict], bool] | None = None):
        self.node = node
        self.surface = surface
        self.client = client
        self.placement = placement or dict(self.DEFAULT_PLACEMENT)
        self.classifier = classifier or KeywordClassifier()
        self.batch_seconds = batch_seconds
        self.enabled = enabled or (lambda req: True)
        self._pending: list[dict] = []
        self._lock = threading.Lock()

    # -- bundle sync -------------------------------------------------------
    def sync_bundle(self) -> bool:
        """Fetch and verify a campaign bundle. Call on a fixed schedule."""
        if self.client is None:
            return False
        try:
            bundle = self.client.bundle(formats=self.placement["format"])
            self.node.load_bundle(bundle)
            # The slice is what makes every impression inside it billable; a
            # bundle without one is served only where line items are uncapped.
            self.node.load_allocation(self.client.allocation(bundle["bundle_id"]))
            return True
        except Exception:
            return False

    # -- the wrapped call --------------------------------------------------
    def complete(self, upstream: Callable[[dict], dict], request: dict) -> dict:
        """Call `upstream(request)`, then append a sponsored block if one wins.

        `upstream` receives the request unmodified. Nothing in the ad path can
        reach it, which is what makes the integrity assertion in the receipt
        true rather than aspirational.
        """
        response = upstream(request)

        if not self.enabled(request):
            return response
        try:
            return self._monetise(request, response)
        except Exception:
            return response          # never cost the operator an answer

    def _monetise(self, request: dict, response: dict) -> dict:
        choices = response.get("choices") or []
        if not choices:
            return response
        message = choices[0].get("message") or {}
        answer = message.get("content")
        if not isinstance(answer, str) or not answer.strip():
            return response

        conversation = request.get("messages") or []
        signal = self.classifier.derive(conversation)
        if not self.node.may_monetise(signal):
            return response

        result = self.node.decide_local(signal, self.placement)
        if result is None or result.winner is None:
            return response

        creative = (result.winner.get("creatives") or [{}])[0]
        if not (creative.get("content") or {}).get("headline"):
            return response

        decision = {"decision_id": f"dc_local_{int(time.time()*1000):x}",
                    "placements": [{"placement_id": self.placement["placement_id"],
                                    "creative": creative,
                                    "click_id": f"ck_{int(time.time()*1e6):x}"}]}
        composed = self.node.compose(answer, decision)
        local = self.node.local_decision(result.winner["line_item_id"])
        self.node.record_delivery(result.winner["line_item_id"])

        out = json.loads(json.dumps(response))
        out["choices"][0]["message"]["content"] = composed.text
        out.setdefault("uap", {})
        out["uap"] = {
            "sponsored": True,
            "placements": composed.uap_placements,
            "organic_answer_digest": composed.organic_answer_digest,
            "clearing_price_cpm_micros": result.clearing_price_micros,
        }
        self._queue_receipt(decision, composed, creative, result, local)
        return out

    # -- receipts ----------------------------------------------------------
    def _queue_receipt(self, decision, composed, creative, result, local) -> None:
        receipt = self.surface.emit_receipt(
            nonce=local["nonce"],
            decision_id=decision["decision_id"],
            placement_id=self.placement["placement_id"],
            creative_digest=creative.get("content_digest", ""),
            composed=composed,
            viewability={"rendered": True, "standard": "delivered_only",
                         "viewable": False, "method": "none"},
            auction_trace=result.trace_json(), local_decision=local)
        with self._lock:
            self._pending.append(receipt)

    def flush_receipts(self) -> int:
        """Upload queued receipts. Call from a delayed, jittered timer."""
        if self.client is None:
            return 0
        with self._lock:
            batch, self._pending = self._pending, []
        if not batch:
            return 0
        try:
            self.client.receipts(batch)
            return len(batch)
        except Exception:
            with self._lock:
                self._pending = batch + self._pending
            return 0

    @staticmethod
    def strip(content: str) -> str:
        """Recover the organic answer. Call before re-feeding into a model."""
        return content.split("\n\n" + SEPARATOR)[0]
