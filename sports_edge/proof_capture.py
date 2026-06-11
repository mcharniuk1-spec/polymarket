from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .goal_audit import DURABLE_DAILY_PROOF_PATH, LIVE_SOURCE_PROOF_PATH, PRODUCTION_CRON_PROOF_PATH


REQUIRED_CRON_JOBS = ("collector_15m", "sofia_daily")
REQUIRED_LIVE_CATEGORIES = ("macroeconomics", "politics", "stocks_trade")
SUCCESSFUL_RUN_STATUSES = {"success", "duplicate_skipped"}


def load_json_file(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Evidence JSON must be an object.")
    return payload


def build_production_cron_proof(evidence: dict[str, Any]) -> dict[str, Any]:
    """Build a sanitized production cron proof from approved, pre-sanitized evidence."""
    run = _dict_value(evidence, "run")
    scheduled_jobs = _dict_value(evidence, "scheduledJobs")
    checks = _dict_value(evidence, "checks")
    normalized_jobs = {job_id: _normalize_job(job_id, _dict_value(scheduled_jobs, job_id)) for job_id in REQUIRED_CRON_JOBS}
    derived_checks = {
        "collector_15m_completed": _job_completed(normalized_jobs["collector_15m"]),
        "sofia_daily_completed": _job_completed(normalized_jobs["sofia_daily"]),
        "source_mode_live": all(job.get("sourceMode") == "live" for job in normalized_jobs.values()),
        "paper_trading_only": _bool_check(checks, "paper_trading_only"),
        "durable_storage_gate_passed": _bool_check(checks, "durable_storage_gate_passed"),
        "logs_contain_credentials": _negative_check(checks, "logs_contain_credentials"),
        "dashboard_reflects_run": _bool_check(checks, "dashboard_reflects_run"),
        "wallet_or_order_execution_enabled": _negative_check(checks, "wallet_or_order_execution_enabled"),
    }
    proof_id_suffix = _safe_suffix(str(run.get("id") or run.get("runId") or evidence.get("asOf") or "manual"))
    return {
        "proof_id": f"production_cron_run_{proof_id_suffix}",
        "researchOnly": True,
        "paperTradingOnly": True,
        "run": {
            "id": run.get("id") or run.get("runId"),
            "event": run.get("event"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "workflow": run.get("workflow"),
            "url": _safe_url(run.get("url") or run.get("html_url")),
        },
        "scheduledJobs": normalized_jobs,
        "checks": derived_checks,
        "notes": [
            "Generated from operator-approved sanitized cron evidence.",
            "Do not include raw logs, tokens, database URLs, cookies, or credentials in this proof artifact.",
        ],
    }


def validate_production_cron_proof(proof: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    run = _dict_value(proof, "run")
    checks = _dict_value(proof, "checks")
    scheduled_jobs = _dict_value(proof, "scheduledJobs")
    if not str(proof.get("proof_id", "")).startswith("production_cron_run_"):
        errors.append("proof_id must start with production_cron_run_")
    if proof.get("researchOnly") is not True:
        errors.append("researchOnly must be true")
    if proof.get("paperTradingOnly") is not True:
        errors.append("paperTradingOnly must be true")
    if run.get("event") not in {"schedule", "vercel_cron"}:
        errors.append("run.event must be schedule or vercel_cron")
    if run.get("status") not in {"completed", "success"}:
        errors.append("run.status must be completed or success")
    if run.get("conclusion") not in {"success", None}:
        errors.append("run.conclusion must be success or null")
    for job_id in REQUIRED_CRON_JOBS:
        job = _dict_value(scheduled_jobs, job_id)
        if not job.get("observed"):
            errors.append(f"{job_id}.observed must be true")
        if job.get("status") not in SUCCESSFUL_RUN_STATUSES:
            errors.append(f"{job_id}.status must be success or duplicate_skipped")
        if job.get("sourceMode") != "live":
            errors.append(f"{job_id}.sourceMode must be live")
    expected_checks = {
        "collector_15m_completed": True,
        "sofia_daily_completed": True,
        "source_mode_live": True,
        "paper_trading_only": True,
        "durable_storage_gate_passed": True,
        "logs_contain_credentials": False,
        "dashboard_reflects_run": True,
        "wallet_or_order_execution_enabled": False,
    }
    for key, expected in expected_checks.items():
        if checks.get(key) is not expected:
            errors.append(f"checks.{key} must be {str(expected).lower()}")
    return errors


def write_production_cron_proof(evidence: dict[str, Any], proof_out: str = PRODUCTION_CRON_PROOF_PATH, dry_run: bool = False) -> dict[str, Any]:
    proof = build_production_cron_proof(evidence)
    errors = validate_production_cron_proof(proof)
    payload = {
        "ok": not errors,
        "dryRun": dry_run,
        "researchOnly": True,
        "paperTradingOnly": True,
        "proofPath": proof_out,
        "proof": proof,
        "validationErrors": errors,
    }
    if errors:
        payload["written"] = False
        return payload
    if dry_run:
        payload["written"] = False
        payload["reason"] = "dry_run"
        return payload
    proof_path = Path(proof_out)
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["written"] = True
    return payload


def build_durable_daily_proof(evidence: dict[str, Any]) -> dict[str, Any]:
    """Build sanitized proof for durable daily write and duplicate-run protection."""
    first_run = _dict_value(evidence, "firstRun")
    duplicate_run = _dict_value(evidence, "duplicateRun")
    storage = _dict_value(evidence, "storage")
    checks = _dict_value(evidence, "checks")
    proof_id_suffix = _safe_suffix(str(first_run.get("runId") or first_run.get("id") or first_run.get("idempotencyKey") or evidence.get("asOf") or "manual"))
    return {
        "proof_id": f"durable_daily_write_{proof_id_suffix}",
        "researchOnly": True,
        "paperTradingOnly": True,
        "firstRun": _normalize_daily_run(first_run),
        "duplicateRun": _normalize_daily_run(duplicate_run),
        "storage": {
            "durable": _bool_check(storage, "durable"),
            "storageMode": storage.get("storageMode"),
        },
        "checks": {
            "duplicate_write_protected": _bool_check(checks, "duplicate_write_protected"),
            "dry_run": _negative_check(checks, "dry_run"),
            "logs_contain_credentials": _negative_check(checks, "logs_contain_credentials"),
            "wallet_or_order_execution_enabled": _negative_check(checks, "wallet_or_order_execution_enabled"),
        },
        "notes": [
            "Generated from operator-approved sanitized durable daily evidence.",
            "This artifact stores run status and idempotency proof only, not database URLs, credentials, cookies, or raw logs.",
        ],
    }


def validate_durable_daily_proof(proof: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    first_run = _dict_value(proof, "firstRun")
    duplicate_run = _dict_value(proof, "duplicateRun")
    storage = _dict_value(proof, "storage")
    checks = _dict_value(proof, "checks")
    if not str(proof.get("proof_id", "")).startswith("durable_daily_write_"):
        errors.append("proof_id must start with durable_daily_write_")
    if proof.get("researchOnly") is not True:
        errors.append("researchOnly must be true")
    if proof.get("paperTradingOnly") is not True:
        errors.append("paperTradingOnly must be true")
    if first_run.get("sourceMode") != "fixture":
        errors.append("firstRun.sourceMode must be fixture")
    if first_run.get("status") != "success":
        errors.append("firstRun.status must be success")
    if first_run.get("storageWritten") is not True:
        errors.append("firstRun.storageWritten must be true")
    if not str(first_run.get("idempotencyKey", "")).startswith("daily:"):
        errors.append("firstRun.idempotencyKey must start with daily:")
    if duplicate_run.get("status") != "duplicate_skipped":
        errors.append("duplicateRun.status must be duplicate_skipped")
    if duplicate_run.get("storageWritten") is not False:
        errors.append("duplicateRun.storageWritten must be false")
    if duplicate_run.get("idempotencyKey") != first_run.get("idempotencyKey"):
        errors.append("duplicateRun.idempotencyKey must match firstRun.idempotencyKey")
    expected_checks = {
        "duplicate_write_protected": True,
        "dry_run": False,
        "logs_contain_credentials": False,
        "wallet_or_order_execution_enabled": False,
    }
    if storage.get("durable") is not True:
        errors.append("storage.durable must be true")
    for key, expected in expected_checks.items():
        if checks.get(key) is not expected:
            errors.append(f"checks.{key} must be {str(expected).lower()}")
    return errors


def write_durable_daily_proof(evidence: dict[str, Any], proof_out: str = DURABLE_DAILY_PROOF_PATH, dry_run: bool = False) -> dict[str, Any]:
    proof = build_durable_daily_proof(evidence)
    errors = validate_durable_daily_proof(proof)
    payload = {
        "ok": not errors,
        "dryRun": dry_run,
        "researchOnly": True,
        "paperTradingOnly": True,
        "proofPath": proof_out,
        "proof": proof,
        "validationErrors": errors,
    }
    if errors:
        payload["written"] = False
        return payload
    if dry_run:
        payload["written"] = False
        payload["reason"] = "dry_run"
        return payload
    proof_path = Path(proof_out)
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["written"] = True
    return payload


def build_live_source_proof(evidence: dict[str, Any]) -> dict[str, Any]:
    """Build sanitized live-source validation proof from approved public-source evidence."""
    run = _dict_value(evidence, "run")
    categories = _dict_value(evidence, "categories")
    checks = _dict_value(evidence, "checks")
    normalized_categories = {
        category: _normalize_live_category(category, _dict_value(categories, category)) for category in REQUIRED_LIVE_CATEGORIES
    }
    proof_id_suffix = _safe_suffix(str(run.get("id") or run.get("runId") or evidence.get("asOf") or "manual"))
    return {
        "proof_id": f"live_source_validation_{proof_id_suffix}",
        "researchOnly": True,
        "paperTradingOnly": True,
        "run": {
            "id": run.get("id") or run.get("runId"),
            "sourceMode": run.get("sourceMode"),
            "asOf": run.get("asOf") or evidence.get("asOf"),
            "command": run.get("command"),
        },
        "categories": normalized_categories,
        "checks": {
            "read_only_public_sources": _bool_check(checks, "read_only_public_sources"),
            "tos_review_completed": _bool_check(checks, "tos_review_completed"),
            "parser_verified_numeric_observations": _bool_check(checks, "parser_verified_numeric_observations"),
            "source_health_only_not_decision_evidence": _bool_check(checks, "source_health_only_not_decision_evidence"),
            "rules_resolution_captured": _bool_check(checks, "rules_resolution_captured"),
            "live_resolution_proof_validated": _bool_check(checks, "live_resolution_proof_validated"),
            "resolved_outcome_public_proof_url_captured": _bool_check(checks, "resolved_outcome_public_proof_url_captured"),
            "wallet_or_order_execution_enabled": _negative_check(checks, "wallet_or_order_execution_enabled"),
            "logs_contain_credentials": _negative_check(checks, "logs_contain_credentials"),
        },
        "notes": [
            "Generated from operator-approved sanitized live-source evidence.",
            "This artifact stores validation counts and booleans only, not raw source payloads, credentials, cookies, or private logs.",
        ],
    }


def validate_live_source_proof(proof: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    run = _dict_value(proof, "run")
    checks = _dict_value(proof, "checks")
    categories = _dict_value(proof, "categories")
    if not str(proof.get("proof_id", "")).startswith("live_source_validation_"):
        errors.append("proof_id must start with live_source_validation_")
    if proof.get("researchOnly") is not True:
        errors.append("researchOnly must be true")
    if proof.get("paperTradingOnly") is not True:
        errors.append("paperTradingOnly must be true")
    if run.get("sourceMode") != "live":
        errors.append("run.sourceMode must be live")
    for category in REQUIRED_LIVE_CATEGORIES:
        row = _dict_value(categories, category)
        if row.get("observed") is not True:
            errors.append(f"categories.{category}.observed must be true")
        if row.get("sourceCount", 0) < 1:
            errors.append(f"categories.{category}.sourceCount must be at least 1")
        if row.get("parserVerifiedObservationCount", 0) < 1:
            errors.append(f"categories.{category}.parserVerifiedObservationCount must be at least 1")
    expected_checks = {
        "read_only_public_sources": True,
        "tos_review_completed": True,
        "parser_verified_numeric_observations": True,
        "source_health_only_not_decision_evidence": True,
        "rules_resolution_captured": True,
        "live_resolution_proof_validated": True,
        "resolved_outcome_public_proof_url_captured": True,
        "wallet_or_order_execution_enabled": False,
        "logs_contain_credentials": False,
    }
    for key, expected in expected_checks.items():
        if checks.get(key) is not expected:
            errors.append(f"checks.{key} must be {str(expected).lower()}")
    return errors


def write_live_source_proof(evidence: dict[str, Any], proof_out: str = LIVE_SOURCE_PROOF_PATH, dry_run: bool = False) -> dict[str, Any]:
    proof = build_live_source_proof(evidence)
    errors = validate_live_source_proof(proof)
    payload = {
        "ok": not errors,
        "dryRun": dry_run,
        "researchOnly": True,
        "paperTradingOnly": True,
        "proofPath": proof_out,
        "proof": proof,
        "validationErrors": errors,
    }
    if errors:
        payload["written"] = False
        return payload
    if dry_run:
        payload["written"] = False
        payload["reason"] = "dry_run"
        return payload
    proof_path = Path(proof_out)
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["written"] = True
    return payload


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _normalize_job(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job_id,
        "observed": bool(job.get("observed")),
        "status": job.get("status"),
        "sourceMode": job.get("sourceMode"),
        "idempotencyKey": job.get("idempotencyKey"),
        "runId": job.get("runId"),
        "scheduledFor": job.get("scheduledFor"),
    }


def _normalize_daily_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": row.get("runId") or row.get("id"),
        "sourceMode": row.get("sourceMode"),
        "status": row.get("status"),
        "idempotencyKey": row.get("idempotencyKey"),
        "storageWritten": row.get("storageWritten") is True,
    }


def _job_completed(job: dict[str, Any]) -> bool:
    return bool(job.get("observed")) and job.get("status") in SUCCESSFUL_RUN_STATUSES and job.get("sourceMode") == "live"


def _normalize_live_category(category: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": category,
        "observed": bool(row.get("observed")),
        "sourceCount": _non_negative_int(row.get("sourceCount")),
        "parserVerifiedObservationCount": _non_negative_int(row.get("parserVerifiedObservationCount")),
        "marketRuleCount": _non_negative_int(row.get("marketRuleCount")),
        "resolutionProofCount": _non_negative_int(row.get("resolutionProofCount")),
    }


def _non_negative_int(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _bool_check(checks: dict[str, Any], key: str) -> bool:
    return checks.get(key) is True


def _negative_check(checks: dict[str, Any], key: str) -> bool | None:
    if key not in checks:
        return None
    return checks.get(key) is True


def _safe_suffix(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value).strip("_")
    return safe or "manual"


def _safe_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
