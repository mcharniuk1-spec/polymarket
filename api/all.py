from sports_edge.dashboard_api import load_scoped_compat_dashboard
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(load_scoped_compat_dashboard(), cache_seconds=0)
