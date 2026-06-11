from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .codex_queue import drain_codex_queue, queue_summary
from .dashboard_api import (
    legacy_scope_disabled_payload,
    load_scoped_compat_dashboard,
    runs_history_payload,
    runs_latest_payload,
    section_payload,
)
from .dashboard_data import build_dashboard_payload, build_report_text
from .intelligence import load_latest_intelligence, run_intelligence_cycle
from .managed_pipeline import load_correlations, load_latest_dashboard, load_model_state, load_run_history, run_managed_cycle
from .orchestrator import CollectorRunConfig, DailyRunConfig, run_collector, run_daily_analysis
from .state_store import blob_storage_enabled, durable_storage_configured


ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
CONTRACT_API_ROUTES = {
    "/api/status": "status",
    "/api/freshness": "freshness",
    "/api/context": "context",
    "/api/candidates": "candidates",
    "/api/decisions": "decisions",
    "/api/models": "models",
    "/api/sources": "sources",
    "/api/portfolio": "portfolio",
    "/api/performance": "performance",
    "/api/performance-contract": "performance",
    "/api/warnings": "warnings",
    "/api/dashboard-contract": "all",
    "/api/runs/latest": "runs_latest",
    "/api/runs/history": "runs_history",
}


def health_payload() -> dict[str, object]:
    return {
        "ok": True,
        "research_only": True,
        "service": "polymarket-research-dashboard",
        "runtime": "local",
        "durable_storage_configured": durable_storage_configured(),
        "blob_storage_enabled": blob_storage_enabled(),
        "cron_secret_configured": bool(os.environ.get("CRON_SECRET")),
        "safety": {
            "walletActions": False,
            "orderExecution": False,
            "credentialStorage": False,
            "realMoneyBetting": False,
        },
    }


class DashboardState:
    def __init__(self) -> None:
        self.refresh()

    def refresh(self, source_mode: str = "fixture", target_count: int = 300) -> None:
        self.payload_data = build_dashboard_payload(source_mode=source_mode, target_count=target_count, use_cache=False)
        self.intelligence_payload = run_intelligence_cycle(
            cycle_type="post_ingestion",
            source_mode=source_mode,
            target_count=target_count,
            persist=True,
            allow_codex=True,
            dashboard_payload={"multi_agent": self.payload_data.get("multi_agent", {})},
        )

    def payload(self) -> dict[str, object]:
        return self.payload_data


STATE: DashboardState | None = None


def get_state() -> DashboardState:
    global STATE
    if STATE is None:
        STATE = DashboardState()
    return STATE


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        route = urlparse(self.path).path
        if route.startswith("/downloads/") or route in {"/", "/styles.css", "/app.js", "/favicon.ico", "/api/health", "/api/summary", "/api/forecasts", "/api/odds-history", "/api/report", "/api/all", "/api/multi-agent", "/api/intelligence", "/api/intelligence-refresh", "/api/cron-refresh", "/api/cron-collector", "/api/cron-daily", "/api/codex-queue", "/api/run-history", "/api/model-state", "/api/correlation-matrix", *CONTRACT_API_ROUTES}:
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_error(404, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/":
            return self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        if route == "/styles.css":
            return self._send_file(WEB_DIR / "styles.css", "text/css; charset=utf-8")
        if route == "/app.js":
            return self._send_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
        if route == "/favicon.ico":
            return self._send_file(WEB_DIR / "favicon.svg", "image/svg+xml")
        if route.startswith("/downloads/"):
            return self._send_download(route)
        if route == "/api/health":
            return self._send_json(health_payload())
        if route == "/api/summary":
            return self._send_json(legacy_scope_disabled_payload("summary"))
        if route == "/api/forecasts":
            return self._send_json(legacy_scope_disabled_payload("forecasts"))
        if route == "/api/odds-history":
            return self._send_json(legacy_scope_disabled_payload("odds-history"))
        if route == "/api/report":
            return self._send_text(build_report_text(), "text/markdown; charset=utf-8")
        if route == "/api/all":
            return self._send_json(load_scoped_compat_dashboard())
        if route in CONTRACT_API_ROUTES:
            if CONTRACT_API_ROUTES[route] == "runs_latest":
                return self._send_json(runs_latest_payload())
            if CONTRACT_API_ROUTES[route] == "runs_history":
                return self._send_json(runs_history_payload())
            return self._send_json(section_payload(CONTRACT_API_ROUTES[route]))
        if route == "/api/multi-agent":
            latest = load_latest_dashboard()
            state = get_state()
            return self._send_json(latest["multi_agent"] if latest else state.payload().get("multi_agent", {}))
        if route == "/api/intelligence":
            latest = load_latest_intelligence()
            return self._send_json(latest or getattr(get_state(), "intelligence_payload", {}))
        if route == "/api/intelligence-refresh":
            state = get_state()
            state.intelligence_payload = run_intelligence_cycle(
                cycle_type="manual",
                source_mode="fixture",
                target_count=300,
                persist=True,
                allow_codex=True,
                dashboard_payload=state.payload(),
            )
            return self._send_json(state.intelligence_payload)
        if route == "/api/cron-refresh":
            params = parse_qs(parsed.query)
            source_mode = params.get("source", ["live"])[0]
            if source_mode not in {"fixture", "live"}:
                source_mode = "live"
            target_count = int(params.get("target_count", ["300"])[0])
            return self._send_json(run_managed_cycle(source_mode=source_mode, target_count=target_count))
        if route == "/api/cron-collector":
            params = parse_qs(parsed.query)
            source_mode = params.get("source", ["fixture"])[0]
            if source_mode not in {"fixture", "live"}:
                source_mode = "fixture"
            return self._send_json(
                run_collector(
                    CollectorRunConfig(
                        source_mode=source_mode,
                        target_count=int(params.get("target_count", ["80"])[0]),
                        dry_run=params.get("dry_run", ["true"])[0].lower() == "true",
                        as_of=params.get("as_of", [None])[0],
                        force=params.get("force", ["false"])[0].lower() == "true",
                    )
                )
            )
        if route == "/api/cron-daily":
            params = parse_qs(parsed.query)
            source_mode = params.get("source", ["fixture"])[0]
            if source_mode not in {"fixture", "live"}:
                source_mode = "fixture"
            return self._send_json(
                run_daily_analysis(
                    DailyRunConfig(
                        source_mode=source_mode,
                        target_count=int(params.get("target_count", ["30"])[0]),
                        dry_run=params.get("dry_run", ["true"])[0].lower() == "true",
                        as_of=params.get("as_of", [None])[0],
                        force=params.get("force", ["false"])[0].lower() == "true",
                    )
                )
            )
        if route == "/api/codex-queue":
            params = parse_qs(parsed.query)
            if params.get("action", ["summary"])[0] == "drain":
                limit = int(params.get("limit", ["12"])[0])
                return self._send_json(drain_codex_queue(limit=limit))
            return self._send_json(queue_summary())
        if route == "/api/run-history":
            return self._send_json(load_run_history())
        if route == "/api/model-state":
            return self._send_json(load_model_state())
        if route == "/api/correlation-matrix":
            return self._send_json(load_correlations())
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/api/refresh":
            params = parse_qs(parsed.query)
            source_mode = params.get("source", ["fixture"])[0]
            target_count = int(params.get("target_count", ["300"])[0])
            state = get_state()
            state.refresh(source_mode=source_mode, target_count=target_count)
            return self._send_json(state.payload())
        if route == "/api/codex-queue":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["12"])[0])
            return self._send_json(drain_codex_queue(limit=limit))
        self.send_error(404, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404, "Not found")
            return
        self._send_bytes(path.read_bytes(), content_type)

    def _send_download(self, route: str) -> None:
        name = Path(route.removeprefix("/downloads/")).name
        path = WEB_DIR / "downloads" / name
        if path.suffix == ".pdf":
            return self._send_file(path, "application/pdf")
        if path.suffix == ".xlsx":
            return self._send_file(
                path,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        self.send_error(404, "Not found")

    def _send_json(self, payload: object) -> None:
        self._send_bytes(json.dumps(payload, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8")

    def _send_text(self, payload: str, content_type: str) -> None:
        self._send_bytes(payload.encode("utf-8"), content_type)

    def _send_bytes(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sports odds research dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Research-only dashboard running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
