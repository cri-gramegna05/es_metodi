#!/usr/bin/env python3
"""A fake Telegram Bot API for dry runs: accepts sendMessage and logs the text.

    python scripts/fake_telegram.py --port 18080 --out data/telegram.log
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

OUT: Path | None = None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        method = urlparse(self.path).path.rsplit("/", 1)[-1]
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if method != "sendMessage":
            return self._json({"ok": False, "description": f"unsupported: {method}"}, 400)
        text = payload.get("text", "")
        line = f"--- to chat {payload.get('chat_id')} ---\n{text}\n"
        sys.stderr.write(line)
        if OUT:
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(line)
        self._json({"ok": True, "result": {"message_id": 1, "text": text}})

    def _json(self, body: dict, status: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    OUT = args.out
    if OUT:
        OUT.parent.mkdir(parents=True, exist_ok=True)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
