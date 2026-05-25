from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
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
        self.storage_mode = "vercel_blob" if self.token else "local_file"

    def read_json(self, key: str, default: Any = None) -> Any:
        local_path = self._local_path(key)
        if local_path.exists():
            return json.loads(local_path.read_text(encoding="utf-8"))
        if self.token:
            remote = self._read_blob_json(key)
            if remote is not None:
                return remote
        return default

    def write_json(self, key: str, payload: Any) -> dict[str, Any]:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        local_path = self._local_path(key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(encoded)
        result = {
            "key": key,
            "localPath": str(local_path),
            "storageMode": "local_file",
            "durable": False,
            "blobMirrored": False,
        }
        if self.token:
            blob_result = self._write_blob(key, encoded)
            result.update(blob_result)
        return result

    def _local_path(self, key: str) -> Path:
        safe_key = key.strip("/").replace("..", "_")
        return self.local_root / safe_key

    def _blob_path(self, key: str) -> str:
        return f"{self.prefix}/{key.strip('/')}"

    def _write_blob(self, key: str, encoded: bytes) -> dict[str, Any]:
        try:
            import vercel_blob  # type: ignore

            response = vercel_blob.put(
                self._blob_path(key),
                encoded,
                {"addRandomSuffix": "false", "contentType": "application/json"},
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
            import vercel_blob  # type: ignore

            listing = vercel_blob.list({"prefix": self._blob_path(key), "limit": "10"})
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


def default_store() -> JsonStateStore:
    return JsonStateStore()
