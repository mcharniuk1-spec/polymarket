from sports_edge.dashboard_data import build_dashboard_payload
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(build_dashboard_payload())
