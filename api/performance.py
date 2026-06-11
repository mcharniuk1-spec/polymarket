from sports_edge.dashboard_api import section_payload
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(section_payload("performance"), cache_seconds=0)
