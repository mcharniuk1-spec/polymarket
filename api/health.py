import os

from sports_edge.state_store import blob_storage_enabled, durable_storage_configured
from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(
            {
                "ok": True,
                "research_only": True,
                "service": "polymarket-research-dashboard",
                "runtime": "vercel",
                "durable_storage_configured": durable_storage_configured(),
                "blob_storage_enabled": blob_storage_enabled(),
                "cron_secret_configured": bool(os.environ.get("CRON_SECRET")),
                "safety": {
                    "walletActions": False,
                    "orderExecution": False,
                    "credentialStorage": False,
                    "realMoneyBetting": False,
                },
            },
            cache_seconds=0,
        )
