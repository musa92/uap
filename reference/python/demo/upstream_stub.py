#!/usr/bin/env python3
"""A stand-in OpenAI-compatible completions server, for the compose demo.

Exists so `docker compose up` needs no GPU and no model download. It answers
every /v1/chat/completions with a fixed reply in the OpenAI response shape,
which is all the proxy needs in order to demonstrate the flow.

Replace this service with vLLM, SGLang, Ollama or anything else that speaks
the same endpoint; nothing else in the compose file changes.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWER = ("Kyoto ryokan rates peak in November for the autumn foliage. Expect "
          "25,000 to 60,000 yen per person per night with dinner and breakfast "
          "included. Book two to three months ahead.")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            req = {}
        body = json.dumps({
            "id": "chatcmpl-stub", "object": "chat.completion",
            "model": req.get("model", "stub"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": ANSWER}}],
            "usage": {"prompt_tokens": 24, "completion_tokens": 41, "total_tokens": 65},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"stub upstream on :{port}  (stands in for vLLM, Ollama, llama.cpp)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
