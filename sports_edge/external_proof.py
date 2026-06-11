from __future__ import annotations

from typing import Any

from .goal_audit import build_goal_audit
from .goal_audit import POSTGRES_PROOF_PATH, PRODUCTION_CRON_PROOF_PATH
from .production_readiness import build_production_readiness
from .state_store import configured_database_url


def build_external_proof_bundle(as_of: str | None = None) -> dict[str, Any]:
    """Describe remaining external proof without performing writes or network calls."""
    audit = build_goal_audit()
    readiness = build_production_readiness()
    return {
        "ok": True,
        "complete": False,
        "researchOnly": True,
        "paperTradingOnly": True,
        "asOf": as_of,
        "safeDefaults": {
            "doesNotDeploy": True,
            "doesNotWriteDatabase": True,
            "doesNotCallLiveApis": True,
            "doesNotUseWallets": True,
            "doesNotPlaceOrders": True,
            "secretsMasked": True,
        },
        "localEvidence": {
            "goalAuditSummary": audit.get("summary", {}),
            "productionReadinessOk": readiness.get("ok", False),
            "productionReadinessCheckCount": len(readiness.get("checks", [])),
        },
        "configuredEnvironment": {
            "databaseUrlPresent": bool(configured_database_url()),
            "databaseUrlValueExposed": False,
        },
        "proofItems": _proof_items(),
        "recommendedSequence": [
            "postgres_apply_proof",
            "durable_daily_write_proof",
            "approved_live_source_validation",
            "vercel_dashboard_smoke_proof",
            "production_cron_run_proof",
        ],
        "completionRule": (
            "Keep goal-audit incomplete until every proof item has human-approved external evidence captured "
            "from the real database, live read-only sources, deployed dashboard, and scheduled production jobs."
        ),
    }


def _proof_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "postgres_apply_proof",
            "status": "approval_required",
            "whyRequired": "The migration SQL must be applied and verified against the real durable Postgres database.",
            "safeDryRunCommand": "python3 -m sports_edge.cli migrate --dry-run",
            "approvedCommand": f"python3 -m sports_edge.cli migrate --proof-out {POSTGRES_PROOF_PATH}",
            "proofPath": POSTGRES_PROOF_PATH,
            "requires": ["approved DATABASE_URL or POSTGRES_URL", "operator approval for durable schema writes"],
            "expectedEvidence": [
                "ok=true",
                "applied=true",
                "storage.durable=true",
                "missingTables=[]",
                "verifiedTables includes all 13 milestone tables",
                "researchOnly=true and paperTradingOnly=true",
                "no database URL or secret value appears in logs",
                "wallet_or_order_execution_enabled=false",
            ],
            "writesDurableState": True,
            "callsNetwork": True,
        },
        {
            "id": "durable_daily_write_proof",
            "status": "approval_required",
            "whyRequired": "The daily analytical run must prove duplicate-safe durable persistence, not only dry-run JSON shape.",
            "safeDryRunCommand": "python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run",
            "approvedCommand": "python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --force",
            "requires": ["approved durable storage environment", "migration already applied"],
            "expectedEvidence": [
                "ok=true",
                "storage.written=true",
                "cronRun.status=success",
                "daily:YYYY-MM-DD idempotency key recorded once",
                "repeat run without --force returns duplicate_skipped",
            ],
            "writesDurableState": True,
            "callsNetwork": False,
        },
        {
            "id": "approved_live_source_validation",
            "status": "approval_required",
            "whyRequired": "Live Polymarket and official external adapters must be validated against approved public sources.",
            "safeDryRunCommand": "python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run",
            "approvedCommand": "python3 -m sports_edge.cli run-daily --source live --dry-run",
            "requires": ["network approval", "source-specific ToS/access review", "read-only public endpoints only"],
            "expectedEvidence": [
                "sourceMode=live",
                "paperTradingOnly=true",
                "no wallet/signing/order execution fields enabled",
                "external observations with parser-verified numeric metrics where available",
                "source-health-only rows remain non-decision evidence",
                "rules/resolution criteria captured for candidates",
            ],
            "writesDurableState": False,
            "callsNetwork": True,
        },
        {
            "id": "vercel_dashboard_smoke_proof",
            "status": "approval_required",
            "whyRequired": "The deployed dashboard/API must be externally reachable and show the contract routes.",
            "safeDryRunCommand": "python3 -m sports_edge.cli production-readiness",
            "approvedCommand": "curl -sS https://<approved-vercel-url>/api/dashboard-contract",
            "requires": ["approved deployed URL", "deployment approval"],
            "expectedEvidence": [
                "HTTP 200 from /api/health",
                "HTTP 200 from /api/dashboard-contract",
                "HTTP 200 from /api/runs/latest",
                "researchOnly=true",
                "paperTradingOnly=true",
                "dashboard warnings/errors visible when present",
            ],
            "writesDurableState": False,
            "callsNetwork": True,
        },
        {
            "id": "production_cron_run_proof",
            "status": "approval_required",
            "whyRequired": "Scheduled GitHub Actions or worker cron must run successfully outside local dry-run mode.",
            "safeDryRunCommand": "python3 -m sports_edge.cli production-readiness",
            "approvedCommand": f"python3 -m sports_edge.cli production-cron-proof --evidence-in <sanitized-cron-evidence.json> --proof-out {PRODUCTION_CRON_PROOF_PATH}",
            "proofPath": PRODUCTION_CRON_PROOF_PATH,
            "requires": ["GitHub Actions access", "durable storage secrets configured", "no secret values copied into reports"],
            "expectedEvidence": [
                "15-minute collector job completed with sourceMode=live",
                "Sofia daily job completed once for the local date",
                "durable storage gate passed",
                "logs contain no credentials",
                "dashboard run status reflects the scheduled run",
            ],
            "writesDurableState": True,
            "callsNetwork": True,
        },
    ]
