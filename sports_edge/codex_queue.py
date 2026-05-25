from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .codex_review import codex_ready_state, run_local_codex_review


REPO_ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE_DIR = REPO_ROOT / "data" / "generated" / "intelligence"
QUEUE_DIR = INTELLIGENCE_DIR / "codex_queue"
PENDING_DIR = QUEUE_DIR / "pending"
PROCESSED_DIR = QUEUE_DIR / "processed"
FAILED_DIR = QUEUE_DIR / "failed"
INDEX_PATH = QUEUE_DIR / "index.json"
DEFAULT_REVIEW_MARKET_LIMIT = 12


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_codex_queue_item(
    payload: dict[str, Any],
    *,
    reason: str,
    review_market_limit: int = DEFAULT_REVIEW_MARKET_LIMIT,
) -> dict[str, Any]:
    cycle_id = str(payload["id"])
    analyses = payload.get("marketAnalysisResults", [])
    compact_analyses = [_compact_analysis(row) for row in analyses[:review_market_limit]]
    market_ids = [str(row.get("id", row.get("marketSlug", ""))) for row in analyses]
    digest_basis = {
        "cycleId": cycle_id,
        "cycleStartedAt": payload.get("cycleStartedAt"),
        "summary": payload.get("summary", {}),
        "marketIds": market_ids,
    }
    digest = hashlib.sha1(json.dumps(digest_basis, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
    return {
        "schema_version": 1,
        "id": f"codexq-{cycle_id}",
        "cycleId": cycle_id,
        "cycleType": payload.get("cycleType"),
        "cycleStartedAt": payload.get("cycleStartedAt"),
        "createdAt": payload.get("createdAt"),
        "queuedAt": iso_now(),
        "status": "pending",
        "attempts": 0,
        "reason": reason,
        "payloadDigest": digest,
        "sourceMode": payload.get("sourceMode"),
        "targetCount": payload.get("targetCount"),
        "inputSnapshot": payload.get("inputSnapshot", {}),
        "summary": payload.get("summary", {}),
        "localCodexAtCollection": payload.get("localCodex", {}),
        "reviewMarketLimit": review_market_limit,
        "reviewMarketCount": len(compact_analyses),
        "totalMarketCount": len(analyses),
        "marketAnalysisIds": market_ids,
        "reviewAnalyses": compact_analyses,
        "researchOnly": True,
    }


def emit_or_enqueue_codex_review(
    payload: dict[str, Any],
    *,
    persist: bool,
    reason: str,
    queue_dir: Path = QUEUE_DIR,
) -> dict[str, Any]:
    if payload.get("localCodex", {}).get("status") == "success":
        return {
            "status": "not_needed",
            "message": "Local Codex review already completed for this cycle.",
            "summary": queue_summary(queue_dir=queue_dir),
        }
    if persist:
        return enqueue_codex_review(payload, reason=reason, queue_dir=queue_dir)
    item = build_codex_queue_item(payload, reason=reason)
    return {
        "status": "emitted_not_persisted",
        "message": "Queue item is included in this response only. Hosted Vercel persistence requires an external durable store or scheduler capture.",
        "itemId": item["id"],
        "cycleId": item["cycleId"],
        "storageMode": "response_only",
        "durable": False,
        "pendingCount": queue_summary(queue_dir=queue_dir)["pendingCount"],
        "queueItem": item,
    }


def enqueue_codex_review(
    payload: dict[str, Any],
    *,
    reason: str,
    queue_dir: Path = QUEUE_DIR,
) -> dict[str, Any]:
    item = build_codex_queue_item(payload, reason=reason)
    result = import_codex_queue_item(item, queue_dir=queue_dir)
    result["message"] = "Codex review queued for ordered local backfill."
    return result


def import_codex_queue_item(item: dict[str, Any], *, queue_dir: Path = QUEUE_DIR) -> dict[str, Any]:
    _require_queue_item(item)
    pending_dir, processed_dir, failed_dir = _queue_dirs(queue_dir)
    item_id = str(item["id"])
    pending_path = pending_dir / f"{item_id}.json"
    processed_path = processed_dir / f"{item_id}.json"
    failed_path = failed_dir / f"{item_id}.json"
    if processed_path.exists():
        return {
            "status": "already_processed",
            "itemId": item_id,
            "cycleId": item["cycleId"],
            "storageMode": "local_file",
            "durable": True,
            **queue_summary(queue_dir=queue_dir),
        }
    if failed_path.exists():
        return {
            "status": "already_failed",
            "itemId": item_id,
            "cycleId": item["cycleId"],
            "storageMode": "local_file",
            "durable": True,
            **queue_summary(queue_dir=queue_dir),
        }
    if pending_path.exists():
        existing = _read_json(pending_path)
        _upsert_index(existing, queue_dir=queue_dir)
        return {
            "status": "already_pending",
            "itemId": item_id,
            "cycleId": item["cycleId"],
            "storageMode": "local_file",
            "durable": True,
            **queue_summary(queue_dir=queue_dir),
        }
    _atomic_write_json(pending_path, item)
    _upsert_index(item, queue_dir=queue_dir)
    return {
        "status": "queued",
        "itemId": item_id,
        "cycleId": item["cycleId"],
        "storageMode": "local_file",
        "durable": True,
        **queue_summary(queue_dir=queue_dir),
    }


def queue_summary(*, queue_dir: Path = QUEUE_DIR) -> dict[str, Any]:
    pending_dir, processed_dir, failed_dir = _queue_dirs(queue_dir, create=False)
    pending = _items_in_dir(pending_dir)
    processed = _items_in_dir(processed_dir)
    failed = _items_in_dir(failed_dir)
    oldest = pending[0] if pending else None
    newest = pending[-1] if pending else None
    readiness = codex_ready_state()
    return {
        "storageMode": "local_file",
        "durable": True,
        "pendingCount": len(pending),
        "processedCount": len(processed),
        "failedCount": len(failed),
        "oldestPendingCycleStartedAt": oldest.get("cycleStartedAt") if oldest else None,
        "newestPendingCycleStartedAt": newest.get("cycleStartedAt") if newest else None,
        "codexReady": {
            "ready": readiness["ready"],
            "enabled": readiness["enabled"],
            "status": readiness["status"],
            "message": readiness["message"],
        },
    }


def list_pending_queue_items(*, queue_dir: Path = QUEUE_DIR, limit: int | None = None) -> list[dict[str, Any]]:
    pending_dir, _, _ = _queue_dirs(queue_dir, create=False)
    items = _items_in_dir(pending_dir)
    if limit is None:
        return items
    return items[: max(limit, 0)]


def drain_codex_queue(
    *,
    limit: int = 12,
    max_attempts: int = 3,
    queue_dir: Path = QUEUE_DIR,
) -> dict[str, Any]:
    readiness = codex_ready_state()
    if not readiness["ready"]:
        summary = queue_summary(queue_dir=queue_dir)
        return {
            "status": "skipped",
            "message": readiness["message"],
            "processed": [],
            "failed": [],
            "processedCount": 0,
            "failedThisRunCount": 0,
            **summary,
        }

    pending_dir, processed_dir, failed_dir = _queue_dirs(queue_dir)
    processed_rows = []
    failed_rows = []
    for item in list_pending_queue_items(queue_dir=queue_dir, limit=limit):
        item_id = str(item["id"])
        pending_path = pending_dir / f"{item_id}.json"
        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["lastAttemptAt"] = iso_now()
        review = run_local_codex_review(item.get("reviewAnalyses", []), str(item.get("cycleStartedAt") or item["lastAttemptAt"]))
        if review.get("status") == "success":
            item["status"] = "processed"
            item["processedAt"] = iso_now()
            item["codexReview"] = review
            _atomic_write_json(processed_dir / f"{item_id}.json", item)
            if pending_path.exists():
                pending_path.unlink()
            _upsert_index(item, queue_dir=queue_dir)
            processed_rows.append({"itemId": item_id, "cycleId": item["cycleId"], "processedAt": item["processedAt"]})
            continue

        item["lastCodexStatus"] = review.get("status", "failed")
        item["lastError"] = review.get("message", "Codex review failed.")
        if item["attempts"] >= max_attempts:
            item["status"] = "failed"
            item["failedAt"] = iso_now()
            _atomic_write_json(failed_dir / f"{item_id}.json", item)
            if pending_path.exists():
                pending_path.unlink()
            failed_rows.append({"itemId": item_id, "cycleId": item["cycleId"], "error": item["lastError"]})
        else:
            _atomic_write_json(pending_path, item)
        _upsert_index(item, queue_dir=queue_dir)

    summary = queue_summary(queue_dir=queue_dir)
    return {
        "status": "success" if processed_rows and not failed_rows else "partial" if processed_rows or failed_rows else "empty",
        "message": "Codex queue drain completed in chronological order.",
        "processed": processed_rows,
        "failed": failed_rows,
        "processedCount": len(processed_rows),
        "failedThisRunCount": len(failed_rows),
        **summary,
    }


def _compact_analysis(row: dict[str, Any]) -> dict[str, Any]:
    news_context = row.get("newsContext", {})
    return {
        "id": row.get("id"),
        "marketSlug": row.get("marketSlug"),
        "marketTitle": row.get("marketTitle"),
        "category": row.get("category"),
        "marketSnapshot": row.get("marketSnapshot", {}),
        "modelInterpretation": row.get("modelInterpretation", {}),
        "newsContext": {
            "tier1Count": int(news_context.get("tier1Count", 0)),
            "tier2Count": int(news_context.get("tier2Count", 0)),
            "tier3Count": int(news_context.get("tier3Count", 0)),
            "strongestSources": news_context.get("strongestSources", [])[:3],
        },
        "decisionCommentary": row.get("decisionCommentary", {}),
        "reliability": row.get("reliability", {}),
        "status": row.get("status"),
    }


def _require_queue_item(item: dict[str, Any]) -> None:
    required = {"id", "cycleId", "cycleStartedAt", "reviewAnalyses", "researchOnly"}
    missing = sorted(required - set(item))
    if missing:
        raise ValueError(f"queue item missing required fields: {', '.join(missing)}")
    if item.get("researchOnly") is not True:
        raise ValueError("queue item must be researchOnly=true")
    if not isinstance(item.get("reviewAnalyses"), list):
        raise ValueError("queue item reviewAnalyses must be a list")


def _queue_dirs(queue_dir: Path, *, create: bool = True) -> tuple[Path, Path, Path]:
    pending_dir = queue_dir / "pending"
    processed_dir = queue_dir / "processed"
    failed_dir = queue_dir / "failed"
    if create:
        for path in (pending_dir, processed_dir, failed_dir):
            path.mkdir(parents=True, exist_ok=True)
    return pending_dir, processed_dir, failed_dir


def _items_in_dir(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for file_path in sorted(path.glob("*.json")):
        try:
            rows.append(_read_json(file_path))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(rows, key=lambda row: (str(row.get("cycleStartedAt", "")), str(row.get("queuedAt", "")), str(row.get("id", ""))))


def _upsert_index(item: dict[str, Any], *, queue_dir: Path) -> None:
    index_path = queue_dir / "index.json"
    rows = []
    if index_path.exists():
        try:
            rows = _read_json(index_path)
        except json.JSONDecodeError:
            rows = []
    by_id = {row["id"]: row for row in rows if isinstance(row, dict) and row.get("id")}
    by_id[item["id"]] = {
        "id": item["id"],
        "cycleId": item["cycleId"],
        "cycleStartedAt": item.get("cycleStartedAt"),
        "queuedAt": item.get("queuedAt"),
        "status": item.get("status"),
        "attempts": item.get("attempts", 0),
        "processedAt": item.get("processedAt"),
        "failedAt": item.get("failedAt"),
        "reason": item.get("reason"),
    }
    rows = sorted(by_id.values(), key=lambda row: (str(row.get("cycleStartedAt", "")), str(row.get("queuedAt", ""))))[-512:]
    _atomic_write_json(index_path, rows)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
