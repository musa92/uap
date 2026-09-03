#!/usr/bin/env python3
"""The same flow as end_to_end.py, but over a real socket.

Starts an exchange on localhost, then drives it with the middleware a provider
would actually install in front of an OpenAI-compatible inference server.

Run:  python3 demo/over_http.py
"""
import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from uap import Exchange, KeyRing, KeywordClassifier, Node, SigningKey, Surface
from uap.middleware import ExchangeClient, UAPMiddleware
from uap.server import make_server

BOLD, DIM, GRN, RST = "\033[1m", "\033[2m", "\033[32m", "\033[0m"
HOST, PORT = "127.0.0.1", 8788


def build_exchange():
    key = SigningKey.generate("uax-ed25519-2026-08")
    ux = Exchange("uax.example.com", key, take_rate_bps=2000, floor_cpm_micros=10_000_000)
    ux.add_line_item({
        "line_item_id": "li_991",
        "advertiser": {"id": "brand.acme.example", "display_name": "Acme Travel"},
        "targeting": {"all": [{"intent_any": ["travel.accommodation.hotel"]},
                              {"commercial_intent_gte": 0.5}]},
        "pricing": {"model": "cpm", "bid_cpm_micros": 62_000_000},
        "categories": ["travel.accommodation"],
        "creatives": [{"creative_id": "cr_884", "format": "sponsored_card",
                       "content_digest": "sha256:" + "5b" * 32,
                       "content": {"brand_name": "Acme Travel",
                                   "headline": "Kyoto ryokan, free cancellation",
                                   "body": "Traditional inns from $180/night.",
                                   "actions": [{"type": "link", "label": "See rooms",
                                                "url": "https://acme.example/kyoto"}]},
                       "disclosure": {"label": "Sponsored", "advertiser_name": "Acme Travel"}}]})
    return ux, key


def fake_inference_server(request):
    """Stands in for vLLM, Ollama, llama.cpp or any hosted provider."""
    return {"id": "chatcmpl-demo", "object": "chat.completion",
            "model": request.get("model", "kimi-k2"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content":
                             "Kyoto ryokan rates peak in November for the autumn "
                             "foliage. Expect 25,000 to 60,000 yen per person per "
                             "night with dinner and breakfast included."}}],
            "usage": {"prompt_tokens": 24, "completion_tokens": 41, "total_tokens": 65}}


def main() -> int:
    ux, exchange_key = build_exchange()
    server = make_server(ux, HOST, PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"{BOLD}exchange listening on http://{HOST}:{PORT}{RST}\n")

    agent = "node.provider.example; role=serving_node; profile=uap.core,uap.decision.local; v=2026-09-02"
    client = ExchangeClient(f"http://{HOST}:{PORT}", agent)

    print(f"{BOLD}1. Discovery over HTTP{RST}")
    manifest = client.manifest()
    print(f"   GET /.well-known/uap          {manifest['entity']['id']}  "
          f"profiles={len(manifest['profiles'])}  "
          f"floor=USD {manifest['auction']['default_floor_cpm_micros']/1e6:.2f} CPM")
    jwks = client.jwks()
    print(f"   GET /.well-known/jwks.json    {jwks['keys'][0]['kid']} ({jwks['keys'][0]['crv']})")

    surface_key = SigningKey.generate("surface-ed25519-01")
    ux.enrol("node.provider.example", surface_key.verifying_key, trust_tier=1)
    ring = KeyRing().add(exchange_key.verifying_key)
    node = Node("node.provider.example", "hf:moonshotai/Kimi-K2-Instruct",
                signing_key=SigningKey.generate("node-1"), exchange_keys=ring, trust_tier=1,
                accept_unverified_classifier=True)
    surface = Surface("node.provider.example", surface_key, trust_tier=1)
    ads = UAPMiddleware(node, surface, client)

    print(f"\n{BOLD}2. Bundle sync over HTTP{RST}")
    ok = ads.sync_bundle()
    print(f"   GET /uap/v1/bundles           verified={ok}  "
          f"{len(node.bundle['line_items'])} line items")

    print(f"\n{BOLD}3. A completion through the middleware{RST}")
    request = {"model": "kimi-k2", "messages": [
        {"role": "user", "content": "I want to book a ryokan in Kyoto. What should I pay?"}]}
    response = ads.complete(fake_inference_server, request)
    print("   " + response["choices"][0]["message"]["content"].replace("\n", "\n   "))
    print(f"\n   {DIM}uap block returned to the caller:{RST}")
    print(f"   {DIM}sponsored={response['uap']['sponsored']}  "
          f"clearing=USD {response['uap']['clearing_price_cpm_micros']/1e6:.2f} CPM{RST}")
    print(f"   {DIM}organic digest {response['uap']['organic_answer_digest'][:39]}...{RST}")

    print(f"\n{BOLD}4. Receipt upload over HTTP{RST}")
    sent = ads.flush_receipts()
    print(f"   POST /uap/v1/receipts:batch   {sent} receipt(s) uploaded")
    print(f"   {DIM}nonce derived from the signed bundle and reconstructed "
          f"exchange-side; nothing was pre-registered{RST}")

    print(f"\n{BOLD}5. Settlement over HTTP{RST}")
    settlement = client._call("GET", "/uap/v1/settlements/2026-09")
    print(f"   GET /uap/v1/settlements/...   verified={settlement['verified_receipts']}  "
          f"rejected={settlement['rejected_receipts']}")
    for s in settlement["splits"]:
        print(f"     {s['party']:<14} {s['bps']:>5} bps  {s['amount_micros']:>6} micros")

    print(f"\n{BOLD}6. Protocol errors are real HTTP errors{RST}")
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"http://{HOST}:{PORT}/uap/v1/decisions",
                                 data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=2)
    except urllib.error.HTTPError as exc:
        import json as _j
        problem = _j.loads(exc.read())
        print(f"   {GRN}{exc.code}{RST} {problem['code']}  {DIM}{problem['title']}{RST}")

    server.shutdown()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
