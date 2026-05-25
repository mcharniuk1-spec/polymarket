from sports_edge.codex_queue import drain_codex_queue, queue_summary
from sports_edge.vercel_api import JsonHandler, query_int, query_value


class handler(JsonHandler):
    def do_GET(self):
        action = query_value(self.path, "action", "summary")
        if action == "drain":
            self.send_json(drain_codex_queue(limit=query_int(self.path, "limit", 12)), cache_seconds=0)
            return
        self.send_json(queue_summary(), cache_seconds=0)

    def do_POST(self):
        self.send_json(drain_codex_queue(limit=query_int(self.path, "limit", 12)), cache_seconds=0)
