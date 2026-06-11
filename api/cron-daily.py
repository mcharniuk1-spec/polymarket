from sports_edge.orchestrator import DailyRunConfig, run_daily_analysis
from sports_edge.state_store import durable_storage_configured
from sports_edge.vercel_api import JsonHandler, cron_authorized, query_int, query_value


def _durable_storage_configured() -> bool:
    return durable_storage_configured()


class handler(JsonHandler):
    def do_GET(self):
        if not cron_authorized(self.headers):
            self.send_error_json("Unauthorized cron request.", status=401)
            return
        if not _durable_storage_configured():
            self.send_error_json("Durable storage is required for scheduled daily analysis writes.", status=503)
            return
        source_mode = query_value(self.path, "source", "live")
        if source_mode not in {"fixture", "live"}:
            source_mode = "live"
        payload = run_daily_analysis(
            DailyRunConfig(
                source_mode=source_mode,
                target_count=query_int(self.path, "target_count", 30),
                dry_run=query_value(self.path, "dry_run", "false").lower() == "true",
                as_of=query_value(self.path, "as_of", "") or None,
                force=query_value(self.path, "force", "false").lower() == "true",
            )
        )
        self.send_json(payload, cache_seconds=0)
