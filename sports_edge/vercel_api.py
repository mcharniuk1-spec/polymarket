from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse


def query_params(path: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(path).query)


def query_value(path: str, key: str, default: str) -> str:
    return query_params(path).get(key, [default])[0]


def query_int(path: str, key: str, default: int) -> int:
    try:
        return int(query_value(path, key, str(default)))
    except ValueError:
        return default


def cron_authorized(headers: Any) -> bool:
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    return headers.get("Authorization") == f"Bearer {secret}"


class JsonHandler(BaseHTTPRequestHandler):
    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"ok": False, "error": message}, status=status, cache_seconds=0)

    def send_json(self, payload: Any, status: int = 200, cache_seconds: int = 900) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "public, max-age=0")
        self.send_header("CDN-Cache-Control", f"public, max-age={cache_seconds}")
        self.send_header("Vercel-CDN-Cache-Control", f"public, max-age={cache_seconds}, stale-while-revalidate=60")
        self.end_headers()
        self.wfile.write(encoded)

    def send_text(self, payload: str, content_type: str = "text/plain; charset=utf-8", cache_seconds: int = 900) -> None:
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "public, max-age=0")
        self.send_header("CDN-Cache-Control", f"public, max-age={cache_seconds}")
        self.send_header("Vercel-CDN-Cache-Control", f"public, max-age={cache_seconds}, stale-while-revalidate=60")
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
