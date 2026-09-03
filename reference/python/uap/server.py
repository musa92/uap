"""Reference exchange over HTTP.

Implements source/services/supply/rest.openapi.json using the standard library
only. Single-threaded and in-memory: this exists so the protocol can be exercised
over a real socket, not so it can carry production traffic.
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .canonical import canonicalize
from .exchange import Exchange
from .buyside import BuySide

__all__ = ["make_server", "serve"]

PROBLEM = "application/problem+json"


def _problem(status: int, code: str, title: str, detail: str = "", retryable: bool = False) -> dict:
    return {"type": f"https://uap.dev/errors/{code.lower().replace('_', '-')}",
            "title": title, "status": status, "code": code,
            "detail": detail, "retryable": retryable}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    exchange: Exchange = None       # injected by make_server
    base_url: str = ""

    # -- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args):
        if self.server.verbose:
            super().log_message(fmt, *args)

    def _send(self, status: int, payload, content_type="application/json"):
        body = canonicalize(payload) if payload is not None else b""
        self.send_response(status)
        if body:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_header("Content-Length", "0")
        rid = self.headers.get("UAP-Request-Id")
        if rid:
            self.send_header("UAP-Request-Id", rid)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _fail(self, status, code, title, detail=""):
        self._send(status, _problem(status, code, title, detail), PROBLEM)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            self._fail(400, "UAP_SIGNAL_MALFORMED", "Body is not valid JSON", str(exc))
            return ...

    def _require_agent(self) -> bool:
        agent = self.headers.get("UAP-Agent")
        if not agent or "role=" not in agent:
            self._fail(400, "UAP_UNSUPPORTED_VERSION", "Missing or malformed UAP-Agent header",
                       "Expected '<entity-id>; role=<role>; profile=<profiles>; v=<version>'")
            return False
        return True

    # -- routing -----------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        ux = self.exchange

        if path == "/.well-known/uap":
            return self._send(200, ux.manifest(self.base_url + "/uap/v1"))
        if path == "/.well-known/jwks.json":
            return self._send(200, ux.jwks())
        if path == "/.well-known/uap-sellers.json":
            return self._send(200, ux.sellers_declaration())
        if path == "/uap/v1/bundles":
            if not self._require_agent():
                return
            formats = (query.get("formats") or [""])[0].split(",") if query.get("formats") else None
            return self._send(200, ux.issue_bundle(formats=[f for f in (formats or []) if f] or None))
        if path == "/uap/v1/allocations":
            if not self._require_agent():
                return
            entity = re.match(r"\s*([^;]+);", self.headers.get("UAP-Agent", ""))
            bundle_id = (query.get("bundle_id") or [""])[0]
            if not entity or bundle_id not in ux._bundles:
                return self._fail(404, "UAP_BUNDLE_EXPIRED", "No such bundle", bundle_id)
            return self._send(200, ux.issue_allocation(bundle_id, entity.group(1).strip()))
        if (m := re.fullmatch(r"/uap/v1/settlements/(\d{4}-\d{2}(?:-\d{2})?)", path)):
            if not self._require_agent():
                return
            return self._send(200, ux.settlement_record(m.group(1)))
        if (m := re.fullmatch(r"/uap/v1/campaigns/([^/:]+)", path)):
            c = self.buyside.campaigns.get(m.group(1))
            return self._send(200, c) if c else self._fail(404, "UAP_UNSUPPORTED_VERSION", "No such campaign")
        if (m := re.fullmatch(r"/uap/v1/line-items/([^/:]+)", path)):
            li = self.buyside.line_items.get(m.group(1))
            return self._send(200, li) if li else self._fail(404, "UAP_UNSUPPORTED_VERSION", "No such line item")
        if (m := re.fullmatch(r"/uap/v1/creatives/([^/]+)/review", path)):
            cr = self.buyside.creatives.get(m.group(1))
            if not cr:
                return self._fail(404, "UAP_UNSUPPORTED_VERSION", "No such creative")
            return self._send(200, {"creative_id": cr["creative_id"], **cr["review"],
                                    "content_digest": cr["content_digest"]})
        if (m := re.fullmatch(r"/uap/v1/advertisers/([^/]+)/campaigns", path)):
            items = [c for c in self.buyside.campaigns.values() if c.get("advertiser_id") == m.group(1)]
            return self._send(200, {"items": items})
        if path == "/openapi.json":
            return self._send(200, {"note": "served from source/services/supply/rest.openapi.json"})
        return self._fail(404, "UAP_UNSUPPORTED_VERSION", "No such endpoint", path)

    def do_POST(self):
        path = urlparse(self.path).path
        ux = self.exchange
        if not self._require_agent():
            return
        if path in ("/uap/v1/decisions", "/uap/v1/receipts:batch", "/uap/v1/events"):
            if not self.headers.get("Idempotency-Key"):
                return self._fail(400, "UAP_UNSUPPORTED_VERSION", "Idempotency-Key is required",
                                  "Required on all non-idempotent methods; 24 hour replay window")

        body = self._body()
        if body is ...:
            return

        if path == "/uap/v1/decisions":
            try:
                decision = ux.decide(body or {})
            except ValueError as exc:
                return self._fail(400, "UAP_SIGNAL_MALFORMED", "Request rejected", str(exc))
            if decision is None:
                return self._send(204, None)          # no-fill is not an error
            return self._send(200, decision)

        if path == "/uap/v1/receipts:batch":
            receipts = (body or {}).get("receipts")
            if not isinstance(receipts, list) or not receipts:
                return self._fail(400, "UAP_SIGNAL_MALFORMED", "receipts must be a non-empty array")
            results = [ux.verify_receipt(r).to_json() for r in receipts]
            return self._send(200, {"results": results})

        role = re.search(r"role=([a-z_]+)", self.headers.get("UAP-Agent", ""))
        role = role.group(1) if role else ""
        bs = self.buyside
        try:
            if (m := re.fullmatch(r"/uap/v1/advertisers/([^/]+)/campaigns", path)):
                return self._send(201, bs.create_campaign({**(body or {}), "advertiser_id": m.group(1)}))
            if (m := re.fullmatch(r"/uap/v1/campaigns/([^/:]+):(pause|resume)", path)):
                return self._send(200, bs.set_campaign_status(
                    m.group(1), "paused" if m.group(2) == "pause" else "active"))
            if (m := re.fullmatch(r"/uap/v1/campaigns/([^/:]+)/line-items", path)):
                return self._send(201, bs.create_line_item(m.group(1), body or {}))
            if (m := re.fullmatch(r"/uap/v1/line-items/([^/]+)/creatives", path)):
                cr = bs.submit_creative(m.group(1), body or {})
                return self._send(202, {"creative_id": cr["creative_id"], **cr["review"],
                                        "content_digest": cr["content_digest"]})
            if path == "/uap/v1/forecast":
                return self._send(200, bs.forecast(body or {}))
            if path == "/uap/v1/conversions":
                events = (body or {}).get("events") or []
                results = [bs.report_conversion(e, caller_role=role) for e in events]
                if role == "serving_node":
                    return self._fail(403, "UAP_ROLE_FORBIDDEN",
                                      "A serving node cannot report conversions", "SPEC.md §9.2")
                return self._send(200, {"accepted": sum(r["accepted"] for r in results),
                                        "rejected": sum(not r["accepted"] for r in results),
                                        "results": results})
            if path == "/uap/v1/reports":
                return self._send(200, bs.run_report(body or {}))
        except KeyError as exc:
            return self._fail(404, "UAP_UNSUPPORTED_VERSION", "Not found", str(exc))
        except ValueError as exc:
            code = str(exc).split(":")[0] if str(exc).startswith("UAP_") else "UAP_SIGNAL_MALFORMED"
            return self._fail(400, code, "Request rejected", str(exc))

        if path == "/uap/v1/events":
            kind = (body or {}).get("type")
            if kind not in ("click", "dismiss", "expand"):
                return self._fail(400, "UAP_SIGNAL_MALFORMED", "Unsupported event type", str(kind))
            ux.record_event(body)
            return self._send(202, None)

        return self._fail(404, "UAP_UNSUPPORTED_VERSION", "No such endpoint", path)


def make_server(exchange: Exchange, host: str = "127.0.0.1", port: int = 8787, verbose: bool = False,
                buyside: BuySide | None = None):
    handler = type("_Bound", (_Handler,), {
        "exchange": exchange, "base_url": f"http://{host}:{port}",
        "buyside": buyside or BuySide(exchange)})
    server = ThreadingHTTPServer((host, port), handler)
    server.verbose = verbose
    return server


def serve(exchange: Exchange, host: str = "127.0.0.1", port: int = 8787, verbose: bool = True):
    server = make_server(exchange, host, port, verbose)
    print(f"UAP exchange listening on http://{host}:{port}")
    print(f"  manifest  http://{host}:{port}/.well-known/uap")
    print(f"  sellers   http://{host}:{port}/.well-known/uap-sellers.json")
    print(f"  jwks      http://{host}:{port}/.well-known/jwks.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
