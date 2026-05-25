from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PolymarketClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class PolymarketEndpointSet:
    gamma_base: str = "https://gamma-api.polymarket.com"
    clob_base: str = "https://clob.polymarket.com"
    data_base: str = "https://data-api.polymarket.com"


class PolymarketPublicClient:
    """Read-only public API client.

    This client intentionally excludes wallet, credential, signing, and order execution paths.
    """

    def __init__(self, endpoints: PolymarketEndpointSet | None = None, timeout_seconds: float = 12.0) -> None:
        self.endpoints = endpoints or PolymarketEndpointSet()
        self.timeout_seconds = timeout_seconds

    def fetch_gamma_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
    ) -> list[dict[str, Any]]:
        params = {
            "limit": min(max(limit, 1), 500),
            "offset": max(offset, 0),
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": "volume",
            "ascending": "false",
        }
        payload = self._get_json(f"{self.endpoints.gamma_base}/markets", params)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            markets = payload.get("markets") or payload.get("data") or payload.get("results")
            if isinstance(markets, list):
                return [item for item in markets if isinstance(item, dict)]
        return []

    def fetch_order_book(self, token_id: str) -> dict[str, Any]:
        payload = self._get_json(f"{self.endpoints.clob_base}/book", {"token_id": token_id})
        return payload if isinstance(payload, dict) else {}

    def fetch_price_history(
        self,
        token_id: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
        fidelity: int = 60,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"market": token_id, "fidelity": fidelity}
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts
        payload = self._get_json(f"{self.endpoints.clob_base}/prices-history", params)
        return payload if isinstance(payload, dict) else {}

    def fetch_public_trades(self, limit: int = 100, market: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": min(max(limit, 1), 500)}
        if market:
            params["market"] = market
        payload = self._get_json(f"{self.endpoints.data_base}/trades", params)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            trades = payload.get("trades") or payload.get("data") or payload.get("results")
            if isinstance(trades, list):
                return [item for item in trades if isinstance(item, dict)]
        return []

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{url}{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "polymarket-research-mvp/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PolymarketClientError(str(exc)) from exc


def parse_polymarket_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]
