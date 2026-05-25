from sports_edge.dashboard_data import build_dashboard_payload
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        payload = build_dashboard_payload()
        self.send_json({"odds_history": payload["odds_history"]})
