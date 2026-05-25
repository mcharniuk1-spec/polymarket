from sports_edge.managed_pipeline import load_run_history
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(load_run_history(), cache_seconds=0)
