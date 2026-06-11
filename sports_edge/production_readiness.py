from __future__ import annotations

import json
import fnmatch
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "polymarket-15m.yml"
VERCEL_PATH = REPO_ROOT / "vercel.json"

CONTRACT_API_ROUTES = {
    "/api/status": "api/status.py",
    "/api/freshness": "api/freshness.py",
    "/api/context": "api/context.py",
    "/api/candidates": "api/candidates.py",
    "/api/decisions": "api/decisions.py",
    "/api/models": "api/models.py",
    "/api/sources": "api/sources.py",
    "/api/portfolio": "api/portfolio.py",
    "/api/performance": "api/performance.py",
    "/api/performance-contract": "api/performance-contract.py",
    "/api/warnings": "api/warnings.py",
    "/api/dashboard-contract": "api/dashboard-contract.py",
    "/api/runs/latest": "api/runs/latest.py",
    "/api/runs/history": "api/runs/history.py",
    "/api/health": "api/health.py",
    "/api/cron-refresh": "api/cron-refresh.py",
    "/api/cron-collector": "api/cron-collector.py",
    "/api/cron-daily": "api/cron-daily.py",
}


def build_production_readiness() -> dict[str, Any]:
    workflow = _read_text(WORKFLOW_PATH)
    vercel = _read_json(VERCEL_PATH)
    checks = [
        _check_workflow_exists(workflow),
        _check_15m_collector(workflow),
        _check_sofia_daily_windows(workflow),
        _check_daily_live_readonly(workflow),
        _check_durable_storage_gate(workflow),
        _check_non_scheduled_dry_run_fallback(workflow),
        _check_vercel_config(vercel),
        _check_vercel_crons(vercel),
        _check_vercel_hobby_function_budget(),
        _check_contract_routes(),
        _check_health_and_cron_routes(),
        _check_runtime_scope_boundary(),
    ]
    return {
        "ok": all(row["status"] == "pass" for row in checks),
        "researchOnly": True,
        "paperTradingOnly": True,
        "deployed": False,
        "checks": checks,
        "externalProofRequired": [
            "GitHub Actions scheduled run logs",
            "Vercel deployment URL smoke check",
            "Approved database migration/durable-write proof",
            "Approved live-source parser validation",
        ],
    }


def _check_workflow_exists(workflow: str) -> dict[str, Any]:
    return _check(
        "workflow_exists",
        bool(workflow.strip()),
        "GitHub Actions workflow exists.",
        {"path": ".github/workflows/polymarket-15m.yml"},
        "Create the scheduled workflow before relying on automation.",
    )


def _check_15m_collector(workflow: str) -> dict[str, Any]:
    remote_collector = "/api/cron-collector?source=live" in workflow and "CRON_SECRET" in workflow
    local_collector = "run-collector --source live" in workflow
    return _check(
        "collector_15m_live",
        'cron: "*/15 * * * *"' in workflow and (remote_collector or local_collector),
        "15-minute schedule runs read-only live collector through deployed cron or local durable fallback.",
        {"cron": "*/15 * * * *", "remotePath": "/api/cron-collector?source=live", "localCommand": "run-collector --source live"},
        "Wire the 15-minute schedule to the read-only live collector through deployed cron auth or local durable storage.",
    )


def _check_sofia_daily_windows(workflow: str) -> dict[str, Any]:
    return _check(
        "sofia_daily_windows",
        'cron: "0 6 * * *"' in workflow and 'cron: "0 7 * * *"' in workflow,
        "Daily schedule covers Sofia 09:00 DST/standard UTC windows.",
        {"utcWindows": ["0 6 * * *", "0 7 * * *"]},
        "Include both UTC windows and let the orchestrator use the Sofia idempotency key.",
    )


def _check_daily_live_readonly(workflow: str) -> dict[str, Any]:
    remote_daily = "/api/cron-daily?source=live" in workflow and "CRON_SECRET" in workflow
    local_daily = "run-daily --source live" in workflow
    return _check(
        "daily_live_readonly",
        (remote_daily or local_daily) and '"sourceMode": "live"' in workflow,
        "Scheduled daily analytical run uses read-only live data through deployed cron or local durable fallback.",
        {"remotePath": "/api/cron-daily?source=live", "localCommand": "run-daily --source live"},
        "Run scheduled daily analysis with live read-only data, not fixture data.",
    )


def _check_durable_storage_gate(workflow: str) -> dict[str, Any]:
    required = [
        "CRON_SECRET",
        "VERCEL_CRON_URL",
        "DATABASE_URL",
        "POSTGRES_URL",
        "POSTGRES_PRISMA_URL",
        "POSTGRES_URL_NON_POOLING",
    ]
    return _check(
        "durable_storage_gate",
        all(key in workflow for key in required)
        and "Check scheduled execution credentials" in workflow
        and "Missing scheduled cron execution credentials" in workflow,
        "Workflow fails closed when neither deployed cron auth nor local durable storage is configured.",
        {"requiredEnvNames": required},
        "Keep scheduled writes behind deployed cron auth or Postgres durable storage configuration.",
    )


def _check_non_scheduled_dry_run_fallback(workflow: str) -> dict[str, Any]:
    return _check(
        "non_scheduled_dry_run_fallback",
        'EVENT_NAME: ${{ github.event_name }}' in workflow
        and 'if [ "${EVENT_NAME}" = "schedule" ]; then' in workflow
        and "Missing durable storage secret; running non-scheduled fixture dry-run proof." in workflow
        and "run-daily --source fixture --target-count 30 --dry-run" in workflow
        and '"status": "non_scheduled_fixture_dry_run"' in workflow,
        "Push/manual workflow runs prove the contract with a fixture dry-run when durable storage is absent.",
        {"command": "run-daily --source fixture --target-count 30 --dry-run", "scheduledWritesStillFailClosed": True},
        "Allow non-scheduled CI to run a fixture dry-run while keeping scheduled writes behind durable storage.",
    )


def _check_vercel_config(vercel: dict[str, Any]) -> dict[str, Any]:
    rewrites = vercel.get("rewrites", []) if isinstance(vercel, dict) else []
    functions = vercel.get("functions", {}) if isinstance(vercel, dict) else {}
    rewrite_sources = {row.get("source") for row in rewrites if isinstance(row, dict)}
    return _check(
        "vercel_static_and_functions",
        {"/", "/app.js", "/styles.css"}.issubset(rewrite_sources) and "api/*.py" in functions,
        "Vercel config serves static dashboard and Python API functions.",
        {"rewrites": sorted(rewrite_sources), "functions": sorted(functions)},
        "Configure dashboard rewrites and Python API function routing in vercel.json.",
    )


def _check_vercel_crons(vercel: dict[str, Any]) -> dict[str, Any]:
    crons = vercel.get("crons", []) if isinstance(vercel, dict) else []
    rows = [row for row in crons if isinstance(row, dict)]
    schedules = {(row.get("path"), row.get("schedule")) for row in rows}
    required = {
        ("/api/cron-daily", "0 6 * * *"),
        ("/api/cron-daily", "0 7 * * *"),
    }
    return _check(
        "vercel_crons",
        required.issubset(schedules),
        "Vercel cron config exposes deployable Sofia daily automation paths.",
        {"required": sorted(required), "configured": sorted(schedules)},
        "Add Vercel crons for both Sofia daily UTC windows. Keep the 15-minute collector on GitHub Actions for Hobby-plan compatibility.",
    )


def _check_contract_routes() -> dict[str, Any]:
    missing = [route for route, path in CONTRACT_API_ROUTES.items() if not (REPO_ROOT / path).exists()]
    return _check(
        "dashboard_contract_routes",
        not missing,
        "Dashboard contract API route files exist.",
        {"routeCount": len(CONTRACT_API_ROUTES), "missing": missing},
        "Add missing Vercel route shims for dashboard contract sections.",
    )


def _check_vercel_hobby_function_budget() -> dict[str, Any]:
    ignore = _read_vercelignore()
    api_files = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "api").rglob("*.py")
        if "__pycache__" not in path.parts
    )
    deployed = [path for path in api_files if not any(fnmatch.fnmatch(path, pattern) for pattern in ignore)]
    return _check(
        "vercel_hobby_function_budget",
        len(deployed) <= 12,
        "Deployable Vercel function count stays within the Hobby plan limit.",
        {"deployableFunctionCount": len(deployed), "deployableFunctions": deployed},
        "Update .vercelignore or consolidate API routes before deploying on the Hobby plan.",
    )


def _check_health_and_cron_routes() -> dict[str, Any]:
    health = _read_text(REPO_ROOT / "api" / "health.py")
    cron = _read_text(REPO_ROOT / "api" / "cron-refresh.py")
    collector = _read_text(REPO_ROOT / "api" / "cron-collector.py")
    daily = _read_text(REPO_ROOT / "api" / "cron-daily.py")
    return _check(
        "health_and_cron_safety",
        "orderExecution" in health
        and "realMoneyBetting" in health
        and "cron_authorized" in cron
        and "cron_authorized" in collector
        and "cron_authorized" in daily
        and "Durable storage is required" in collector
        and "Durable storage is required" in daily,
        "Health route reports no execution capability and cron route checks authorization.",
        {"healthRoute": "api/health.py", "cronRoutes": ["api/cron-refresh.py", "api/cron-collector.py", "api/cron-daily.py"]},
        "Expose safety status and require cron authorization.",
    )


def _check_runtime_scope_boundary() -> dict[str, Any]:
    app_js = _read_text(REPO_ROOT / "web" / "app.js")
    index_html = _read_text(REPO_ROOT / "web" / "index.html")
    dashboard_data = _read_text(REPO_ROOT / "sports_edge" / "dashboard_data.py")
    dashboard_api = _read_text(REPO_ROOT / "sports_edge" / "dashboard_api.py")
    forbidden_visible_markers = [
        'data-page="sports"',
        "Fixture Backtest",
        "Sports Forecasts",
        "sportsForecastCount",
        "renderSports(",
    ]
    forbidden_dashboard_data_markers = [
        "Backtester().run",
        "OddsIngestion().by_event",
        "OddsMovementAnalyzer.history_rows",
    ]
    passed = (
        not any(marker in index_html or marker in app_js for marker in forbidden_visible_markers)
        and not any(marker in dashboard_data for marker in forbidden_dashboard_data_markers)
        and "legacySportsDisabled" in dashboard_data
        and "legacy_scope_disabled_payload" in dashboard_api
    )
    return _check(
        "runtime_scope_boundary",
        passed,
        "Runtime dashboard/API scope excludes legacy sports backtest surfaces.",
        {
            "activeSections": ["macroeconomics", "politics", "stocks_trade"],
            "visibleForbiddenMarkers": forbidden_visible_markers,
            "legacyRoutesDisabled": "legacy_scope_disabled_payload" in dashboard_api,
        },
        "Remove visible legacy sports dashboard surfaces and keep legacy backtest routes disabled.",
    )


def _check(check_id: str, passed: bool, description: str, evidence: dict[str, Any], remediation: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "pass" if passed else "fail",
        "description": description,
        "evidence": evidence,
        "remediation": None if passed else remediation,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_vercelignore() -> list[str]:
    try:
        return [
            line.strip()
            for line in (REPO_ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    except OSError:
        return []
