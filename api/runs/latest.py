from sports_edge.dashboard_api import runs_latest_payload
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(runs_latest_payload(), cache_seconds=0)
