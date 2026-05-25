from sports_edge.managed_pipeline import load_correlations
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(load_correlations(), cache_seconds=0)
