from sports_edge.intelligence import load_latest_intelligence
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(load_latest_intelligence())
