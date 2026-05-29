import os

from sports_edge.vercel_api import JsonHandler


class handler(JsonHandler):
    def do_GET(self):
        durable_storage_configured = any(
            os.environ.get(key)
            for key in (
                "DATABASE_URL",
                "POSTGRES_URL",
                "POSTGRES_PRISMA_URL",
                "POSTGRES_URL_NON_POOLING",
                "BLOB_READ_WRITE_TOKEN",
            )
        )
        self.send_json(
            {
                "ok": True,
                "research_only": True,
                "service": "polymarket-research-dashboard",
                "runtime": "vercel",
                "durable_storage_configured": durable_storage_configured,
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
