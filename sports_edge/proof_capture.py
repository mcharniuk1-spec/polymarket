from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .goal_audit import PRODUCTION_CRON_PROOF_PATH


REQUIRED_CRON_JOBS = ("collector_15m", "sofia_daily")
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


def _job_completed(job: dict[str, Any]) -> bool:
    return bool(job.get("observed")) and job.get("status") in SUCCESSFUL_RUN_STATUSES and job.get("sourceMode") == "live"


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
