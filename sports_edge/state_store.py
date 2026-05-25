from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_STATE_DIR = REPO_ROOT / "data" / "generated" / "production_state"
DEFAULT_PREFIX = "polymarket/state"


class JsonStateStore:
    """Small JSON state store with local fallback and optional Vercel Blob mirroring."""

    def __init__(self, local_root: Path | str = LOCAL_STATE_DIR, prefix: str | None = None) -> None:
        self.local_root = Path(local_root)
        self.prefix = (prefix or os.environ.get("POLYMARKET_STATE_PREFIX") or DEFAULT_PREFIX).strip("/")
        self.token = os.environ.get("BLOB_READ_WRITE_TOKEN")
        self.local_enabled = not (os.environ.get("VERCEL") or str(REPO_ROOT).startswith("/var/task"))
        self.storage_mode = "vercel_blob" if self.token else "local_file"

    def read_json(self, key: str, default: Any = None) -> Any:
        local_path = self._local_path(key)
        if self.token:
            remote = self._read_blob_json(key)
            if remote is not None:
                return remote
        if self.local_enabled and local_path.exists():
            return json.loads(local_path.read_text(encoding="utf-8"))
        return default

    def write_json(self, key: str, payload: Any) -> dict[str, Any]:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        local_path = self._local_path(key)
        if self.token:
            blob_result = self._write_blob(key, encoded)
            if blob_result.get("durable"):
                return {"key": key, "localPath": None, **blob_result}
            if not self.local_enabled:
                return {"key": key, "localPath": None, **blob_result}
        if not self.local_enabled:
            return {
                "key": key,
                "localPath": None,
                "storageMode": "unavailable",
                "durable": False,
                "blobMirrored": False,
                "error": "Vercel production state requires BLOB_READ_WRITE_TOKEN.",
            }
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(encoded)
        return {
            "key": key,
            "localPath": str(local_path),
            "storageMode": "local_file",
            "durable": False,
            "blobMirrored": False,
        }

    def _local_path(self, key: str) -> Path:
        safe_key = key.strip("/").replace("..", "_")
        return self.local_root / safe_key

    def _blob_path(self, key: str) -> str:
        return f"{self.prefix}/{key.strip('/')}"

    def _write_blob(self, key: str, encoded: bytes) -> dict[str, Any]:
        try:
            response = self._blob_api_request(
                "PUT",
                f"/?{urlencode({'pathname': self._blob_path(key)})}",
                body=encoded,
                extra_headers={
                    "x-vercel-blob-access": "private",
                    "x-add-random-suffix": "0",
                    "x-allow-overwrite": "1",
                    "x-content-type": "application/json",
                },
            )
            return {
                "storageMode": "vercel_blob",
                "durable": True,
                "blobMirrored": True,
                "blob": response,
            }
        except Exception as exc:  # pragma: no cover - depends on deployed Vercel Blob runtime
            return {
                "storageMode": "local_file",
                "durable": False,
                "blobMirrored": False,
                "blobError": str(exc),
            }

    def _read_blob_json(self, key: str) -> Any | None:
        try:
            listing = self._blob_api_request(
                "GET",
                f"?{urlencode({'prefix': self._blob_path(key), 'limit': '10'})}",
            )
            blobs = listing.get("blobs", []) if isinstance(listing, dict) else []
            exact = [row for row in blobs if row.get("pathname") == self._blob_path(key)]
            if not exact:
                return None
            url = exact[0].get("downloadUrl") or exact[0].get("url")
            if not url:
                return None
            request = Request(url, headers={"Authorization": f"Bearer {self.token}"})
            with urlopen(request, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

    def _blob_api_request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("BLOB_READ_WRITE_TOKEN is not configured.")
        store_id = self._blob_store_id()
        request = Request(
            f"https://vercel.com/api/blob{path}",
            data=body,
            method=method,
            headers={
                "authorization": f"Bearer {self.token}",
                "x-api-version": "12",
                "x-api-blob-request-attempt": "0",
                "x-api-blob-request-id": f"{store_id}:{int(time.time() * 1000)}",
                "x-vercel-blob-store-id": store_id,
                **(extra_headers or {}),
            },
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _blob_store_id(self) -> str:
        explicit = os.environ.get("BLOB_STORE_ID")
        if explicit:
            return explicit.removeprefix("store_")
        parts = self.token.split("_") if self.token else []
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        raise RuntimeError("Unable to derive Vercel Blob store id from token.")


def default_store() -> JsonStateStore:
    return JsonStateStore()
