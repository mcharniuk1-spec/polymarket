from sports_edge.dashboard_data import build_dashboard_payload
from sports_edge.managed_pipeline import load_latest_dashboard
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        payload = load_latest_dashboard() or build_dashboard_payload()
        self.send_json(payload["multi_agent"])
