from sports_edge.managed_pipeline import run_managed_cycle
from sports_edge.vercel_api import JsonHandler, cron_authorized, query_int, query_value


class handler(JsonHandler):
    def do_GET(self):
        if not cron_authorized(self.headers):
            self.send_error_json("Unauthorized cron request.", status=401)
            return
        source_mode = query_value(self.path, "source", "live")
        if source_mode not in {"fixture", "live"}:
            source_mode = "live"
        cycle_type = query_value(self.path, "cycle_type", "scheduled_15m")
        if cycle_type not in {"scheduled_15m", "post_ingestion", "manual"}:
            cycle_type = "scheduled_15m"
        payload = run_managed_cycle(
            cycle_type=cycle_type,
            source_mode=source_mode,
            target_count=query_int(self.path, "target_count", 300),
            global_review=query_value(self.path, "global_review", "false").lower() == "true",
        )
        self.send_json(payload, cache_seconds=0)
