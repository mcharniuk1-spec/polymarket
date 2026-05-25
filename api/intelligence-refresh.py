from sports_edge.intelligence import run_intelligence_cycle
from sports_edge.vercel_api import JsonHandler, query_int, query_value


class handler(JsonHandler):
    def do_GET(self):
        source_mode = query_value(self.path, "source", "fixture")
        if source_mode not in {"fixture", "live"}:
            source_mode = "fixture"
        target_count = query_int(self.path, "target_count", 300)
        payload = run_intelligence_cycle(
            cycle_type="manual",
            source_mode=source_mode,
            target_count=target_count,
            persist=False,
            allow_codex=False,
        )
        self.send_json(payload)
