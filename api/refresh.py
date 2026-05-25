from sports_edge.dashboard_data import build_dashboard_payload
from sports_edge.vercel_api import JsonHandler, query_int, query_value


class handler(JsonHandler):
    def do_GET(self):
        self._refresh()

    def do_POST(self):
        self._refresh()

    def _refresh(self):
        source_mode = query_value(self.path, "source", "fixture")
        if source_mode not in {"fixture", "live"}:
            source_mode = "fixture"
        target_count = query_int(self.path, "target_count", 300)
        self.send_json(build_dashboard_payload(source_mode=source_mode, target_count=target_count, use_cache=False))
