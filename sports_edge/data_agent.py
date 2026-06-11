from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .external_adapters import collect_external_adapter_bundle
from .polymarket_client import PolymarketPublicClient, parse_polymarket_list
from .research_scope import ACTIVE_CATEGORIES, CATEGORY_LABELS, normalize_category_id
from .schemas import ExternalObservation, MarketSnapshot, OrderBookSnapshot, SourceRecord, iso_now, stable_id


class DataAgent:
    """Read-only market and external-data normalizer.

    The agent never signs, posts orders, or touches wallet/private endpoints. Live mode only uses
    PolymarketPublicClient's public read methods.
    """

    def __init__(self, client: PolymarketPublicClient | None = None, external_fetcher: Any | None = None) -> None:
        self.client = client or PolymarketPublicClient()
        self.external_fetcher = external_fetcher

    def collect(
        self,
        *,
        run_id: str,
        source_mode: str = "fixture",
        target_count: int = 30,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        observed = observed_at or iso_now()
        if source_mode == "fixture":
            raw_markets = fixture_gamma_markets()
        elif source_mode == "live":
            raw_markets = self.client.fetch_gamma_markets(limit=target_count, offset=0, active=True, closed=False)
        else:
            raise ValueError("source_mode must be fixture or live")

        market_snapshots: list[MarketSnapshot] = []
        order_books: list[OrderBookSnapshot] = []
        warnings: list[str] = []
        for raw in raw_markets:
            snapshot = normalize_gamma_market(raw, run_id=run_id, observed_at=observed)
            if snapshot is None:
                continue
            market_snapshots.append(snapshot)
            token_ids = parse_polymarket_list(raw.get("clobTokenIds"))
            if source_mode == "fixture":
                book = fixture_order_book(token_ids[0] if token_ids else f"{snapshot.market_id}-yes")
            elif token_ids:
                book = self.client.fetch_order_book(str(token_ids[0]))
            else:
                book = {}
                warnings.append(f"market {snapshot.market_id} has no token id for order-book collection")
            if book:
                order_books.append(
                    normalize_order_book(
                        book,
                        run_id=run_id,
                        market_id=snapshot.market_id,
                        token_id=str(token_ids[0] if token_ids else f"{snapshot.market_id}-yes"),
                        observed_at=observed,
                    )
                )
            if len(market_snapshots) >= target_count:
                break

        adapter_bundle = collect_external_adapter_bundle(
            run_id=run_id,
            observed_at=observed,
            source_mode=source_mode,
            fetcher=self.external_fetcher,
        )
        source_records = data_source_records() + adapter_bundle.source_records
        external_observations = adapter_bundle.observations
        warnings.extend(adapter_bundle.warnings)
        validation_errors = _validation_errors(market_snapshots, order_books, external_observations)
        return {
            "ok": not validation_errors,
            "agent": "data_agent",
            "sourceMode": source_mode,
            "runId": run_id,
            "observedAt": observed,
            "activeSections": list(ACTIVE_CATEGORIES),
            "marketSnapshots": [row.to_dict() for row in market_snapshots],
            "orderBookSnapshots": [row.to_dict() for row in order_books],
            "sourceRecords": [row.to_dict() for row in source_records],
            "externalObservations": [row.to_dict() for row in external_observations],
            "freshness": freshness_summary(market_snapshots, order_books, external_observations, observed),
            "warnings": warnings,
            "errors": validation_errors,
        }


def normalize_gamma_market(raw: dict[str, Any], *, run_id: str, observed_at: str) -> MarketSnapshot | None:
    category = infer_market_category(raw)
    if category not in ACTIVE_CATEGORIES:
        return None
    market_id = str(raw.get("id") or raw.get("conditionId") or raw.get("slug") or stable_id(raw.get("question", "")))
    outcomes = [str(item) for item in parse_polymarket_list(raw.get("outcomes"))]
    outcome_prices = [_safe_float(item) for item in parse_polymarket_list(raw.get("outcomePrices"))]
    outcome_prices = [value for value in outcome_prices if value is not None]
    best_bid = _safe_float(raw.get("bestBid"))
    best_ask = _safe_float(raw.get("bestAsk"))
    spread = _safe_float(raw.get("spread"))
    if spread is None and best_bid is not None and best_ask is not None:
        spread = max(best_ask - best_bid, 0.0)
    end_time = _first_text(raw.get("endDate"), raw.get("endDateIso"), raw.get("end_time"))
    return MarketSnapshot(
        snapshot_id=stable_id(run_id, market_id, observed_at),
        run_id=run_id,
        market_id=market_id,
        condition_id=_first_text(raw.get("conditionId")),
        question=_first_text(raw.get("question"), raw.get("title"), default="Untitled Polymarket market"),
        category=category,
        observed_at=observed_at,
        fetched_at=observed_at,
        active=bool(raw.get("active", True)),
        closed=bool(raw.get("closed", False)),
        outcomes=outcomes,
        outcome_prices=outcome_prices,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        liquidity=_safe_float(raw.get("liquidityNum"), raw.get("liquidity")),
        volume_24h=_safe_float(raw.get("volume24hr"), raw.get("volume24h"), raw.get("volume")),
        rules_summary=_first_text(raw.get("description"), raw.get("rules")),
        resolution_criteria=_first_text(raw.get("resolutionSource"), raw.get("resolution_criteria"), raw.get("description")),
        end_time=end_time,
        time_to_resolution_hours=_hours_until(end_time, observed_at),
        source_url=_market_url(raw),
        raw_ref=f"polymarket_gamma:{market_id}",
        payload={"raw": raw},
    )


def normalize_order_book(
    raw: dict[str, Any],
    *,
    run_id: str,
    market_id: str,
    token_id: str,
    observed_at: str,
) -> OrderBookSnapshot:
    bids = _book_rows(raw.get("bids") or raw.get("buy") or [])
    asks = _book_rows(raw.get("asks") or raw.get("sell") or [])
    best_bid = max((row["price"] for row in bids), default=None)
    best_ask = min((row["price"] for row in asks), default=None)
    spread = max(best_ask - best_bid, 0.0) if best_bid is not None and best_ask is not None else None
    return OrderBookSnapshot(
        snapshot_id=stable_id(run_id, market_id, token_id, observed_at),
        run_id=run_id,
        market_id=market_id,
        token_id=token_id,
        observed_at=observed_at,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        bid_depth=round(sum(row["size"] for row in bids), 6),
        ask_depth=round(sum(row["size"] for row in asks), 6),
        bids=bids,
        asks=asks,
        payload={"raw": raw},
    )


def external_observation_contracts(*, run_id: str, observed_at: str) -> list[ExternalObservation]:
    return collect_external_adapter_bundle(
        run_id=run_id,
        observed_at=observed_at,
        source_mode="fixture",
    ).observations


def data_source_records() -> list[SourceRecord]:
    records = [
        SourceRecord(
            source_id="polymarket_gamma",
            name="Polymarket Gamma public markets",
            source_type="market_data",
            category="polymarket",
            reliability_tier="primary",
            access_policy="public_read_only",
            freshness_sla_minutes=15,
            url="https://gamma-api.polymarket.com",
            notes="Market metadata only; no wallet, signing, or order execution.",
        ),
        SourceRecord(
            source_id="polymarket_clob_public",
            name="Polymarket CLOB public order books",
            source_type="market_data",
            category="polymarket",
            reliability_tier="primary",
            access_policy="public_read_only",
            freshness_sla_minutes=15,
            url="https://clob.polymarket.com",
            notes="Public price/order-book reads only.",
        ),
    ]
    return records


def freshness_summary(
    market_snapshots: list[MarketSnapshot],
    order_books: list[OrderBookSnapshot],
    external_observations: list[ExternalObservation],
    observed_at: str,
) -> dict[str, Any]:
    categories = {
        category: {
            "latestMarketObservedAt": None,
            "marketSnapshotCount": 0,
            "externalObservationCount": 0,
            "status": "missing",
        }
        for category in ACTIVE_CATEGORIES
    }
    for row in market_snapshots:
        categories[row.category]["latestMarketObservedAt"] = row.observed_at
        categories[row.category]["marketSnapshotCount"] += 1
        categories[row.category]["status"] = "fresh_contract"
    for row in external_observations:
        categories[row.category]["externalObservationCount"] += 1
    return {
        "observedAt": observed_at,
        "marketSnapshotCount": len(market_snapshots),
        "orderBookSnapshotCount": len(order_books),
        "externalObservationCount": len(external_observations),
        "categories": categories,
        "warnings": _freshness_warnings(external_observations),
    }


def _freshness_warnings(external_observations: list[ExternalObservation]) -> list[str]:
    pending = [row for row in external_observations if row.metric_name == "adapter_readiness"]
    if pending:
        return ["One or more external adapters are pending; those rows must not strengthen paper decisions."]
    return ["External observations are fixture official-source records unless source=live is enabled in a read-only environment."]


def infer_market_category(raw: dict[str, Any]) -> str | None:
    direct = normalize_category_id(_first_text(raw.get("category"), raw.get("categorySlug"), raw.get("section")))
    if direct:
        return direct
    text = " ".join(
        str(value)
        for value in (
            raw.get("question"),
            raw.get("title"),
            raw.get("description"),
            raw.get("slug"),
            raw.get("tags"),
            json.dumps(raw.get("events", []), sort_keys=True) if raw.get("events") else "",
        )
        if value
    ).lower()
    out_of_scope_terms = (
        "spread:",
        "moneyline",
        "point spread",
        "total points",
        "win the match",
        "win the game",
        "home team",
        "away team",
        "arsenal",
        "golden state",
        "valkyries",
        "lakers",
        "nba",
        "wnba",
        "nfl",
        "mlb",
        "nhl",
        "ncaa",
        "champions league",
        "premier league",
        "ufc",
        "t20",
    )
    if any(term in text for term in out_of_scope_terms):
        return None
    if any(term in text for term in ("cpi", "inflation", "fed", "fomc", "gdp", "unemployment", "payroll", "rates")):
        return "macroeconomics"
    if any(term in text for term in ("election", "president", "senate", "congress", "poll", "nomination", "court")):
        return "politics"
    if any(term in text for term in ("stock", "shares", "close above", "close below", "tariff", "trade", "nasdaq", "spy", "nvda", "tsla", "sec filing")):
        return "stocks_trade"
    return None


def fixture_gamma_markets() -> list[dict[str, Any]]:
    return [
        _fixture_market("macro-cpi-june", "Will CPI come in above consensus in the next release?", "macroeconomics", 0.47),
        _fixture_market("politics-election-cert", "Will the election certification deadline be delayed?", "politics", 0.31),
        _fixture_market("stocks-nvda-close", "Will NVDA close above the weekly threshold?", "stocks_trade", 0.54),
    ]


def fixture_order_book(token_id: str) -> dict[str, Any]:
    return {
        "market": token_id,
        "bids": [{"price": "0.49", "size": "120"}, {"price": "0.48", "size": "80"}],
        "asks": [{"price": "0.52", "size": "100"}, {"price": "0.53", "size": "70"}],
    }


def _fixture_market(market_id: str, question: str, category: str, price: float) -> dict[str, Any]:
    return {
        "id": market_id,
        "conditionId": f"condition-{market_id}",
        "question": question,
        "category": category,
        "slug": market_id,
        "active": True,
        "closed": False,
        "outcomes": '["Yes","No"]',
        "outcomePrices": json.dumps([price, round(1.0 - price, 3)]),
        "clobTokenIds": json.dumps([f"token-{market_id}-yes", f"token-{market_id}-no"]),
        "bestBid": round(price - 0.02, 3),
        "bestAsk": round(price + 0.02, 3),
        "liquidityNum": 2500.0,
        "volume24hr": 300.0,
        "endDate": "2026-12-31T23:59:59Z",
        "description": "Fixture market with objective public resolution criteria for schema validation.",
        "resolutionSource": "https://example.com/resolution",
    }


def _validation_errors(
    markets: list[MarketSnapshot],
    books: list[OrderBookSnapshot],
    observations: list[ExternalObservation],
) -> list[dict[str, Any]]:
    rows: list[tuple[str, list[str]]] = []
    rows.extend((f"market:{row.market_id}", row.validate()) for row in markets)
    rows.extend((f"order_book:{row.market_id}:{row.token_id}", row.validate()) for row in books)
    rows.extend((f"external:{row.observation_id}", row.validate()) for row in observations)
    return [{"record": name, "errors": errors} for name, errors in rows if errors]


def _book_rows(rows: Any) -> list[dict[str, float]]:
    normalized = []
    if not isinstance(rows, list):
        return normalized
    for row in rows:
        if isinstance(row, dict):
            price = _safe_float(row.get("price"), row.get("p"))
            size = _safe_float(row.get("size"), row.get("s"))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            price = _safe_float(row[0])
            size = _safe_float(row[1])
        else:
            continue
        if price is None or size is None:
            continue
        normalized.append({"price": price, "size": size})
    return normalized


def _safe_float(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_text(*values: Any, default: str | None = None) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _hours_until(end_time: str | None, observed_at: str) -> float | None:
    if not end_time:
        return None
    try:
        end = _parse_iso(end_time)
        observed = _parse_iso(observed_at)
    except ValueError:
        return None
    return round((end - observed).total_seconds() / 3600, 3)


def _parse_iso(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _market_url(raw: dict[str, Any]) -> str | None:
    slug = raw.get("slug")
    if not slug:
        return None
    return f"https://polymarket.com/event/{slug}"
