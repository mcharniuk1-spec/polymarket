from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import MultiAgentPipeline
from .backtesting import Backtester
from .codex_queue import drain_codex_queue, queue_summary
from .dashboard_enrichment import enrich_multi_agent_payload
from .intelligence import load_latest_intelligence, run_intelligence_cycle
from .managed_pipeline import load_correlations, load_model_state, load_run_history, run_managed_cycle
from .odds_ingestion import OddsIngestion
from .odds_movement import OddsMovementAnalyzer
from .reporting import PerformanceReporter, multi_agent_payload, report_payload


ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
REPORT_PATH = ROOT / "reports/performance_report.md"


class DashboardState:
    def __init__(self) -> None:
        self.refresh()

    def refresh(self, source_mode: str = "fixture", target_count: int = 300) -> None:
        self.result = Backtester().run(write_log=True)
        PerformanceReporter().write(self.result)
        self.multi_agent_result = MultiAgentPipeline().run(source_mode=source_mode, target_count=target_count)
        PerformanceReporter().write_multi_agent(self.multi_agent_result)
        self.intelligence_payload = run_intelligence_cycle(
            cycle_type="post_ingestion",
            source_mode=source_mode,
            target_count=target_count,
            persist=True,
            allow_codex=True,
            dashboard_payload={"multi_agent": enrich_multi_agent_payload(multi_agent_payload(self.multi_agent_result))},
        )
        all_snapshots = []
        for snapshots in OddsIngestion().by_event().values():
            all_snapshots.extend(snapshots)
        self.odds_history = OddsMovementAnalyzer.history_rows(all_snapshots)

    def payload(self) -> dict[str, object]:
        payload = report_payload(self.result)
        payload["odds_history"] = self.odds_history
        payload["multi_agent"] = enrich_multi_agent_payload(multi_agent_payload(self.multi_agent_result))
        return payload


STATE = DashboardState()


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        route = urlparse(self.path).path
        if route in {"/", "/styles.css", "/app.js", "/favicon.ico", "/api/summary", "/api/forecasts", "/api/performance", "/api/odds-history", "/api/report", "/api/all", "/api/multi-agent", "/api/intelligence", "/api/intelligence-refresh", "/api/cron-refresh", "/api/codex-queue", "/api/run-history", "/api/model-state", "/api/correlation-matrix"}:
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
        if route == "/api/summary":
            return self._send_json({"metrics": STATE.result.metrics})
        if route == "/api/forecasts":
            return self._send_json({"forecasts": [item.to_dict() for item in STATE.result.forecasts]})
        if route == "/api/performance":
            return self._send_json({"metrics": STATE.result.metrics, "trades": [item.to_dict() for item in STATE.result.trades]})
        if route == "/api/odds-history":
            return self._send_json({"odds_history": STATE.odds_history})
        if route == "/api/report":
            return self._send_text(REPORT_PATH.read_text(encoding="utf-8"), "text/markdown; charset=utf-8")
        if route == "/api/all":
            return self._send_json(STATE.payload())
        if route == "/api/multi-agent":
            return self._send_json(enrich_multi_agent_payload(multi_agent_payload(STATE.multi_agent_result)))
        if route == "/api/intelligence":
            return self._send_json(getattr(STATE, "intelligence_payload", load_latest_intelligence()))
        if route == "/api/intelligence-refresh":
            STATE.intelligence_payload = run_intelligence_cycle(
                cycle_type="manual",
                source_mode="fixture",
                target_count=300,
                persist=True,
                allow_codex=True,
                dashboard_payload=STATE.payload(),
            )
            return self._send_json(STATE.intelligence_payload)
        if route == "/api/cron-refresh":
            params = parse_qs(parsed.query)
            source_mode = params.get("source", ["live"])[0]
            if source_mode not in {"fixture", "live"}:
                source_mode = "live"
            target_count = int(params.get("target_count", ["300"])[0])
            return self._send_json(run_managed_cycle(source_mode=source_mode, target_count=target_count))
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
            STATE.refresh(source_mode=source_mode, target_count=target_count)
            return self._send_json(STATE.payload())
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
