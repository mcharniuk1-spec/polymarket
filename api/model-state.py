from sports_edge.managed_pipeline import load_model_state
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(load_model_state(), cache_seconds=0)
