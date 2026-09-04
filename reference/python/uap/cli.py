"""The `uap` command.

    uap keygen  [--kid NAME]                 mint an Ed25519 key, print JWK + seed
    uap serve   [--port 8787]                run the reference exchange
    uap proxy   --upstream URL --exchange URL  monetise an OpenAI-compatible server
    uap seed-demo --exchange URL             create a demo advertiser and campaign
    uap validate FILE --schema NAME          validate a JSON document against a schema
    uap decide  --bundle FILE --signal FILE  run a local auction, print the trace
    uap version

Every subcommand is a thin wrapper over the library; nothing here is logic that
an integrator could not call directly.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import auction, predicate
from .crypto import SigningKey
from .version import UAP_VERSION, __version__


def _load(path: str):
    return json.loads(pathlib.Path(path).read_text())


def cmd_keygen(a) -> int:
    key = SigningKey.generate(a.kid)
    out = {"kid": a.kid, "jwk": key.verifying_key.to_jwk(),
           "seed_hex": key._seed.hex(),
           "_note": "Keep seed_hex secret. Publish jwk in your JWKS and enrol it with the exchange."}
    print(json.dumps(out, indent=2))
    return 0


def cmd_serve(a) -> int:
    from .buyside import BuySide
    from .exchange import Exchange
    from .server import make_server
    key = SigningKey.from_seed_hex(a.kid, a.seed) if a.seed else SigningKey.generate(a.kid)
    ux = Exchange(a.entity, key, floor_cpm_micros=a.floor_cpm_micros)
    server = make_server(ux, a.host, a.port, buyside=BuySide(ux))
    print(f"uap exchange {a.entity} on http://{a.host}:{a.port}   kid={a.kid}")
    print(f"  manifest  /.well-known/uap      jwks  /.well-known/jwks.json")
    print(f"  supply    /uap/v1/bundles  /allocations  /decisions  /receipts:batch")
    print(f"  demand    /uap/v1/advertisers/…/campaigns  /forecast  /conversions  /reports")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def cmd_proxy(a) -> int:
    from .proxy import serve_proxy
    return serve_proxy(upstream=a.upstream, exchange=a.exchange, entity=a.entity,
                       model_id=a.model, host=a.host, port=a.port,
                       seed_hex=a.seed, kid=a.kid, ad_every=a.ad_every,
                       accept_unverified_classifier=a.accept_unverified_classifier,
                       enrol=a.enrol)


def cmd_seed_demo(a) -> int:
    """Enrol a demo advertiser and put one campaign live, through the real API.

    An exchange with no demand can never fill, so `docker compose up` on its own
    shows a completion with no ad and looks broken. This walks the same calls an
    advertiser makes, so it seeds the demo and smoke-tests the buy side at once.
    """
    from .demand_client import DemandClient, DemandError

    dsp = DemandClient(a.exchange, advertiser_id=a.advertiser)
    try:
        dsp._call("POST", "/uap/v1/accounts", {
            "entity_id": a.advertiser, "kind": "advertiser", "currency": "USD"})
        print(f"  account   {a.advertiser}")
    except DemandError as exc:
        if exc.problem.get("code") != "UAP_ACCOUNT_EXISTS":
            print(f"  account   skipped ({exc})")

    try:
        c = dsp.create_campaign(name="Demo: Japan travel", objective="reach",
                                budget_micros=5_000_000_000, currency="USD",
                                spend_mandate="ap2:intent:demo", campaign_id="cmp_demo")
        print(f"  campaign  {c['campaign_id']}  status={c['status']}")

        li = dsp.create_line_item(
            c["campaign_id"], line_item_id="li_demo", display_name="Acme Travel",
            targeting={"all": [{"intent_any": ["travel.accommodation.hotel",
                                               "travel.destination.japan"]}]},
            pricing={"model": "cpm", "currency": "USD", "bid_cpm_micros": 42_000_000},
            creative={"creative_id": "cr_demo", "format": "sponsored_card",
                      "content": {"headline": "Kyoto ryokan, free cancellation",
                                  "body": "Traditional inns from $180 a night, "
                                          "cancel up to 24 hours before arrival.",
                                  "brand_name": "Acme Travel",
                                  "actions": [{"type": "link", "label": "See rooms",
                                               "url": "https://acme.example/kyoto"}]},
                      "disclosure": {"label": "Sponsored", "advertiser_name": "Acme Travel"}})
        print(f"  line item {li['line_item_id']}  status={li['status']}  "
              f"creative={li['creatives'][0]['review']['status']}")
    except DemandError as exc:
        print(f"  already seeded ({exc})")
        return 0

    print("  demand is live; a matching turn through the proxy will now fill")
    return 0


def cmd_validate(a) -> int:
    try:
        import jsonschema
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        print("validate needs: pip install 'uap-protocol[dev]'", file=sys.stderr)
        return 2
    root = pathlib.Path(a.schemas)
    registry = Registry()
    for p in root.rglob("*.json"):
        doc = json.loads(p.read_text())
        registry = registry.with_resource(
            doc.get("$id", "https://uap.dev/schemas/" + p.relative_to(root).as_posix()),
            Resource(contents=doc, specification=DRAFT202012))
    uri = a.schema if a.schema.startswith("http") else "https://uap.dev/schemas/" + a.schema
    errors = list(jsonschema.Draft202012Validator({"$ref": uri}, registry=registry)
                  .iter_errors(_load(a.file)))
    for e in errors:
        print(f"  {'/'.join(map(str, e.path)) or '(root)'}: {e.message}")
    print(f"{a.file}: {'valid' if not errors else f'{len(errors)} error(s)'} against {a.schema}")
    return 1 if errors else 0


def cmd_decide(a) -> int:
    bundle, signal = _load(a.bundle), _load(a.signal)
    placement = _load(a.placement) if a.placement else {
        "placement_id": "pl_post_answer", "position": "post_answer", "format": "sponsored_card"}
    compiled = {li["line_item_id"]: predicate.compile_predicate(li["targeting"])
                for li in bundle.get("line_items", []) if li.get("targeting") is not None}
    r = auction.run(bundle.get("line_items", []), signal, placement,
                    floor_cpm_micros=bundle.get("floor_cpm_micros", 0), compiled=compiled)
    for t in r.trace:
        print(f"  {t.line_item_id:<14} {t.outcome:<22} {t.ecpm_micros/1e6:8.2f} CPM")
    if r.winner:
        print(f"winner {r.winner['line_item_id']} clears at {r.clearing_price_micros/1e6:.2f} CPM")
    else:
        print("no fill")
    return 0


def cmd_version(a) -> int:
    print(f"uap-protocol {__version__} (protocol {UAP_VERSION})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="uap", description="Universal Ads Protocol reference tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keygen", help="mint an Ed25519 signing key")
    k.add_argument("--kid", default="uap-ed25519-01")
    k.set_defaults(fn=cmd_keygen)

    s = sub.add_parser("serve", help="run the reference exchange")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8787)
    s.add_argument("--entity", default="uax.local"); s.add_argument("--kid", default="uax-ed25519-01")
    s.add_argument("--seed", help="hex seed; omit to generate an ephemeral key")
    s.add_argument("--floor-cpm-micros", type=int, default=10_000_000)
    s.set_defaults(fn=cmd_serve)

    p = sub.add_parser("proxy", help="monetise an OpenAI-compatible completions server")
    p.add_argument("--upstream", required=True, help="e.g. http://localhost:8000")
    p.add_argument("--exchange", required=True, help="e.g. http://localhost:8787")
    p.add_argument("--entity", default="node.local"); p.add_argument("--model", default="unknown")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8800)
    p.add_argument("--kid", default="surface-ed25519-01"); p.add_argument("--seed")
    p.add_argument("--ad-every", type=int, default=3, help="one placement per N turns")
    p.add_argument("--enrol", action="store_true",
                   help="create a payee account and enrol this key at startup")
    p.add_argument("--accept-unverified-classifier", action="store_true",
                   help="serve on the demo keyword classifier; never in production")
    p.set_defaults(fn=cmd_proxy)

    sd = sub.add_parser("seed-demo", help="create a demo advertiser and campaign")
    sd.add_argument("--exchange", required=True)
    sd.add_argument("--advertiser", default="brand.acme.example")
    sd.set_defaults(fn=cmd_seed_demo)

    v = sub.add_parser("validate", help="validate a JSON file against a UAP schema")
    v.add_argument("file"); v.add_argument("--schema", required=True, help="e.g. supply/ad_request.json")
    v.add_argument("--schemas", default="source/schemas", help="path to the schema tree")
    v.set_defaults(fn=cmd_validate)

    d = sub.add_parser("decide", help="run a local auction from files")
    d.add_argument("--bundle", required=True); d.add_argument("--signal", required=True)
    d.add_argument("--placement")
    d.set_defaults(fn=cmd_decide)

    sub.add_parser("version").set_defaults(fn=cmd_version)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
