#!/usr/bin/env python3
"""A fake Ollama server speaking /api/chat, for running the pipeline without a model.

It answers with the StubBackend's deterministic JSON. With --flaky, the first call for
each brand returns malformed output, so the retry path gets exercised for real.

    python scripts/fake_ollama.py --port 11435 [--flaky]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.classify.backends import StubBackend  # noqa: E402

STUB = StubBackend()
SEEN: set[str] = set()
FLAKY = False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # /api/tags, used as a health check
        self._json({"models": [{"name": "fake-gemma:latest"}]})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        messages = [m for m in payload.get("messages", []) if m.get("role") != "system"]
        text = "\n".join(m.get("content", "") for m in messages)
        brand = (re.search(r"^Brand: (.+)$", text, re.M) or [None, "?"])[1]

        if FLAKY and brand not in SEEN:
            SEEN.add(brand)
            content = "Sure! Here is the analysis:\n{ is_italian: yes, score: 'high' }"
        else:
            content = STUB.generate("", messages, payload.get("format") or {})

        self._json({
            "model": payload.get("model", "fake"),
            "message": {"role": "assistant", "content": content},
            "done": True,
        })

    def _json(self, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("fake-ollama %s\n" % (fmt % args))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--flaky", action="store_true", help="fail the first call per brand")
    args = parser.parse_args()
    FLAKY = args.flaky
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
