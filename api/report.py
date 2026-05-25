from sports_edge.dashboard_data import build_report_text
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_text(build_report_text(), "text/markdown; charset=utf-8")
