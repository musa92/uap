"""One-command monetisation for any OpenAI-compatible server.

    uap proxy --upstream http://localhost:8000 --exchange https://uax.example.com

Sits in front of /v1/chat/completions, forwards the request unchanged, and
appends a disclosed sponsored block to the answer when a local auction fills.
vLLM, SGLang, Ollama, llama.cpp, TGI and LM Studio all expose that endpoint,
so this is the same integration for every one of them.

The upstream call always completes first and is never modified; nothing in the
ad path can reach it. Any error in the ad path returns the upstream answer as
is, so a monetisation problem can never cost the operator a completion.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .crypto import KeyRing, SigningKey, VerifyingKey
from .middleware import ExchangeClient, UAPMiddleware
from .node import Node, Surface

__all__ = ["serve_proxy", "make_proxy"]


def _forward(upstream: str, path: str, body: bytes, headers: dict) -> tuple[int, bytes, str]:
    req = urllib.request.Request(upstream.rstrip("/") + path, data=body, method="POST")
    for h in ("Content-Type", "Authorization"):
        if h in headers:
            req.add_header(h, headers[h])
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "application/json")


def _enrol(client: ExchangeClient, entity: str, key: SigningKey) -> tuple[bool, str]:
    """Create a payee account and bind this signing key to it.

    Without this the exchange cannot map the receipt's kid to an entity, so it
    rejects every receipt with `signature` and the node earns nothing while ads
    render perfectly. Enrolment is also what lifts supply from trust tier 0,
    where CPM cannot be sold at all.
    """
    try:
        account = client._call("POST", "/uap/v1/accounts", {
            "entity_id": entity, "kind": "serving_node", "currency": "USD",
            "payout": {"handler": "dev.uap.payout.ap2", "minimum_micros": 0}})
        client._call("POST", f"/uap/v1/accounts/{account['account_id']}/keys",
                     key.verifying_key.to_jwk())
        return True, account["account_id"]
    except Exception as exc:
        return False, str(exc)


def make_proxy(*, upstream: str, exchange: str, entity: str, model_id: str,
               host: str, port: int, key: SigningKey, ad_every: int,
               accept_unverified_classifier: bool, enrol: bool = False):
    agent = f"{entity}; role=serving_node; profile=uap.core,uap.decision.local,uap.measure; v=2026-09-02"
    client = ExchangeClient(exchange, agent)

    # Trust the exchange's published keys, refreshed with the bundle.
    enrolled, enrol_detail = (False, "not requested")
    if enrol:
        enrolled, enrol_detail = _enrol(client, entity, key)

    ring = KeyRing()
    for jwk in (client.jwks() or {}).get("keys", []):
        ring.add(VerifyingKey.from_jwk(jwk))

    node = Node(entity, model_id, signing_key=key, exchange_keys=ring, trust_tier=1,
                accept_unverified_classifier=accept_unverified_classifier)
    surface = Surface(entity, key, trust_tier=1)
    placement = dict(UAPMiddleware.DEFAULT_PLACEMENT)
    ads = UAPMiddleware(node, surface, client, placement=placement)
    state = {"turns": 0, "filled": 0, "synced": ads.sync_bundle(),
             "enrolled": enrolled, "enrol_detail": enrol_detail}

    def scheduler():
        # Hourly bundle sync, receipts flushed on a delayed cadence. Both are
        # scheduled, not per-turn, which is what §8.2 requires.
        while True:
            time.sleep(60)
            state["synced"] = ads.sync_bundle() or state["synced"]
            ads.flush_receipts()
    threading.Thread(target=scheduler, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, status, body: bytes, ctype="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/uap/status":
                return self._send(200, json.dumps({
                    "entity": entity, "model": model_id, "exchange": exchange,
                    "bundle_loaded": node.bundle is not None,
                    "enrolled": state["enrolled"], "enrolment": state["enrol_detail"],
                    "turns": state["turns"], "filled": state["filled"],
                    "pending_receipts": len(ads._pending)}).encode())
            self._send(404, b'{"error":"not found"}')

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            if self.path != "/v1/chat/completions":
                status, body, ctype = _forward(upstream, self.path, raw, self.headers)
                return self._send(status, body, ctype)

            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                return self._send(400, b'{"error":"invalid json"}')

            # Streaming responses are passed through untouched: an ad appended
            # to a stream would have to be composed before the answer finished,
            # which is exactly what the integrity boundary forbids.
            if request.get("stream"):
                status, body, ctype = _forward(upstream, self.path, raw, self.headers)
                return self._send(status, body, ctype)

            state["turns"] += 1
            def upstream_call(req):
                status, body, _ = _forward(upstream, self.path, json.dumps(req).encode(), self.headers)
                if status != 200:
                    raise RuntimeError(f"upstream {status}")
                return json.loads(body)

            try:
                response = upstream_call(request)
            except Exception as exc:
                return self._send(502, json.dumps({"error": str(exc)}).encode())

            if state["turns"] % max(1, ad_every) == 0:
                out = ads.complete(lambda _r: response, request)
                if out.get("uap", {}).get("sponsored"):
                    state["filled"] += 1
                response = out
            self._send(200, json.dumps(response).encode())

    server = ThreadingHTTPServer((host, port), Handler)
    return server, state, ads


def serve_proxy(*, upstream, exchange, entity, model_id, host, port, seed_hex, kid,
                ad_every, accept_unverified_classifier, enrol=False) -> int:
    key = SigningKey.from_seed_hex(kid, seed_hex) if seed_hex else SigningKey.generate(kid)
    server, state, ads = make_proxy(upstream=upstream, exchange=exchange, entity=entity,
                                    model_id=model_id, host=host, port=port, key=key,
                                    ad_every=ad_every,
                                    accept_unverified_classifier=accept_unverified_classifier,
                                    enrol=enrol)
    print(f"uap proxy on http://{host}:{port}  ->  {upstream}")
    print(f"  exchange {exchange}   bundle {'loaded' if state['synced'] else 'NOT loaded'}   "
          f"kid {kid}   one ad every {ad_every} turns")
    if enrol:
        print(f"  enrolment: {'ok, ' + state['enrol_detail'] if state['enrolled'] else 'FAILED, ' + state['enrol_detail']}")
    elif not state["enrolled"]:
        print("  key is not enrolled: receipts will be rejected and nothing will be paid.")
        print("  enrol it with the exchange, or pass --enrol on a dev exchange.")
    if not accept_unverified_classifier:
        print("  classifier: fail-closed stub; nothing will be served until you plug in a real one")
    print("  point your OpenAI client at this address; GET /uap/status for counters")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ads.flush_receipts()
        server.shutdown()
    return 0
