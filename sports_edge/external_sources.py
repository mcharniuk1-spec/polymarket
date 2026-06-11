from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .agents import ACTIVE_CATEGORIES
from .source_registry import SourceRecord, SourceRegistry


IMPLEMENTED_FULL_SCAN_SOURCES = {"polymarket-gamma", "polymarket-clob"}
CLIENT_AVAILABLE_NOT_WIRED = {"polymarket-data-api"}

COUNTRY_TERMS = (
    "united states",
    "us",
    "usa",
    "china",
    "ukraine",
    "russia",
    "israel",
    "iran",
    "turkey",
    "germany",
    "france",
    "uk",
    "united kingdom",
    "japan",
    "south korea",
    "brazil",
    "india",
    "mexico",
    "canada",
    "australia",
    "european union",
    "eu",
)

POLITICAL_TRENDS = ("election", "poll", "ceasefire", "war", "sanctions", "policy", "vote", "court", "deadline", "tariff")
MACRO_TRENDS = ("fed", "rates", "treasury", "cpi", "inflation", "jobs", "unemployment", "gdp", "oil", "gold", "trade", "tariff")
COMPANY_TICKERS: dict[str, tuple[str, ...]] = {
    "SPY": ("spy", "s&p", "s&p 500"),
    "AAPL": ("aapl", "apple"),
    "MSFT": ("msft", "microsoft"),
    "TSLA": ("tsla", "tesla"),
    "META": ("meta",),
    "AMZN": ("amzn", "amazon"),
    "NVDA": ("nvda", "nvidia"),
    "GOOGL": ("googl", "google", "alphabet"),
    "WTI": ("wti", "oil"),
}
TRADE_TERMS = ("tariff", "trade", "exports", "imports", "customs", "wto", "comtrade", "sanctions")


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_external_data_readiness(
    candidates: list[Any],
    *,
    registry: SourceRegistry | None = None,
    fetched_source_ids: set[str] | None = None,
    decision_at: str | None = None,
) -> dict[str, Any]:
    registry = registry or SourceRegistry()
    fetched = set(fetched_source_ids or IMPLEMENTED_FULL_SCAN_SOURCES)
    rows = [_candidate_dict(candidate) for candidate in candidates]
    return {
        "schema_version": 1,
        "updatedAt": iso_now(),
        "decisionAt": decision_at,
        "research_only": True,
        "sourceStatusSummary": _source_status_summary(registry, fetched),
        "categoryReadiness": [_category_readiness(registry, category, rows, fetched) for category in ACTIVE_CATEGORIES],
        "detectedEntities": _detected_entities(rows),
        "externalSeriesRequirements": _external_series_requirements(),
        "modelingControls": _modeling_controls(),
    }


def _candidate_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    if hasattr(candidate, "to_dict"):
        return candidate.to_dict()
    return {}


def _source_status_summary(registry: SourceRegistry, fetched: set[str]) -> dict[str, Any]:
    counts: Counter[str] = Counter(_adapter_status(source, fetched) for source in registry.active_sources())
    return {
        "fetchedSourceIds": sorted(fetched),
        "statusCounts": dict(counts),
        "rules": [
            "Only implemented fetched sources can strengthen a paper decision.",
            "Registered public sources still need fetchers, entity links, and as-of storage before model use.",
            "Keyed, paid, restricted, manual-licensed, and unofficial sources stay blocked until access and terms are reviewed.",
        ],
    }


def _category_readiness(
    registry: SourceRegistry,
    category: str,
    candidates: list[dict[str, Any]],
    fetched: set[str],
) -> dict[str, Any]:
    category_candidates = [candidate for candidate in candidates if candidate.get("category") == category]
    sources = registry.for_category(category, include_global=True, include_polymarket=True, allowed_only=False)
    source_rows = [_source_row(source, fetched) for source in sources]
    status_counts: Counter[str] = Counter(row["adapterStatus"] for row in source_rows)
    return {
        "category": category,
        "candidateCount": len(category_candidates),
        "eventCount": len({candidate.get("event_id") for candidate in category_candidates}),
        "sourceStatusCounts": dict(status_counts),
        "fetchedSources": [row for row in source_rows if row["adapterStatus"] == "implemented"],
        "plannedSources": [
            row
            for row in source_rows
            if row["adapterStatus"] in {"registered_needs_fetcher_and_asof_storage", "client_available_not_wired"}
        ],
        "blockedSources": [row for row in source_rows if row["adapterStatus"] == "blocked_until_access_or_license_review"],
    }


def _source_row(source: SourceRecord, fetched: set[str]) -> dict[str, Any]:
    return {
        **source.to_dict(),
        "adapterStatus": _adapter_status(source, fetched),
        "canStrengthenDecisionNow": source.id in fetched,
        "requiresAsOfStorage": _requires_asof_storage(source),
    }


def _adapter_status(source: SourceRecord, fetched: set[str]) -> str:
    if source.id in fetched:
        return "implemented"
    if source.id in CLIENT_AVAILABLE_NOT_WIRED:
        return "client_available_not_wired"
    if source.access in {"paid", "restricted", "manual-licensed", "unofficial", "free-key"} or not source.allowed_by_default:
        return "blocked_until_access_or_license_review"
    if _requires_asof_storage(source):
        return "registered_needs_fetcher_and_asof_storage"
    return "registered_planned_or_manual"


def _requires_asof_storage(source: SourceRecord) -> bool:
    source_type = source.source_type
    if source.category in {"macro", "macroeconomics", "stocks_trade"} and "api" in source_type:
        return True
    if source.category in {"geopolitics", "politics"} and any(token in source_type for token in ("api", "feed", "official", "government", "conflict")):
        return True
    if source.category == "global" and any(token in source_type for token in ("trade", "company")):
        return True
    return False


def _detected_entities(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    country_counter: Counter[str] = Counter()
    political_counter: Counter[str] = Counter()
    macro_counter: Counter[str] = Counter()
    company_counter: Counter[str] = Counter()
    trade_counter: Counter[str] = Counter()
    for candidate in candidates:
        text = _candidate_text(candidate)
        for country in COUNTRY_TERMS:
            if _has_term(text, country):
                country_counter[country.upper() if country in {"us", "usa", "uk", "eu"} else country.title()] += 1
        for trend in POLITICAL_TRENDS:
            if _has_term(text, trend):
                political_counter[trend] += 1
        for trend in MACRO_TRENDS:
            if _has_term(text, trend):
                macro_counter[trend] += 1
        _count_keyword_map(company_counter, text, COMPANY_TICKERS)
        for term in TRADE_TERMS:
            if _has_term(text, term):
                trade_counter[term] += 1
    return {
        "countries": _counter_rows(country_counter),
        "politicalTrends": _counter_rows(political_counter),
        "macroTrends": _counter_rows(macro_counter),
        "companiesAndCommodities": _counter_rows(company_counter),
        "tradeSignals": _counter_rows(trade_counter),
    }


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("market_title"),
        candidate.get("outcome"),
        candidate.get("subcategory"),
        candidate.get("category"),
        " ".join(str(actor) for actor in candidate.get("actors", [])),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _count_keyword_map(counter: Counter[str], text: str, keywords: dict[str, tuple[str, ...]]) -> None:
    for label, terms in keywords.items():
        if any(_has_term(text, term) for term in terms):
            counter[label] += 1


def _has_term(text: str, term: str) -> bool:
    if " " in term or "-" in term:
        return term in text
    return f" {term} " in f" {text} "


def _counter_rows(counter: Counter[str], *, limit: int = 24) -> list[dict[str, Any]]:
    return [{"name": key, "count": count} for key, count in counter.most_common(limit)]


def _external_series_requirements() -> list[dict[str, Any]]:
    return [
        {
            "id": "macro_release_calendar",
            "purpose": "Anchor CPI, jobs, GDP, rates, oil, and treasury markets to official release calendars and revision rules.",
            "preferredSourceClass": "BLS, BEA, FRED, Treasury, EIA, ECB, OECD, IMF, and official release feeds.",
        },
        {
            "id": "political_event_timeline",
            "purpose": "Track elections, sanctions, votes, courts, diplomacy, and conflict events with as-of timestamps.",
            "preferredSourceClass": "official election boards, Congress/regulations APIs, UN/NATO/EU feeds, ACLED/UCDP where access permits.",
        },
        {
            "id": "stocks_trade_market_data",
            "purpose": "Separate stock/index price thresholds, filings, tariff decisions, trade flows, and commodity-linked equity shocks.",
            "preferredSourceClass": "SEC EDGAR, official exchange closes, USTR/WTO/UN Comtrade/Census trade releases, and public company filings.",
        },
        {
            "id": "source_asof_storage",
            "purpose": "Persist release time, fetched time, source URL, entity mapping, and transformation so no future model uses post-decision data.",
            "preferredSourceClass": "project state store plus immutable source snapshots.",
        },
    ]


def _modeling_controls() -> dict[str, Any]:
    return {
        "asOfRule": "A feature is eligible only when source observed_at/released_at/fetched_at is at or before decision_at.",
        "endogeneityRule": "Sibling Polymarket markets and same-event markets are exposure constraints, not causal instruments.",
        "correlationRule": "Use overlapping timestamp windows; mark fallback-derived, sparse, or weak-link correlations as diagnostic only.",
        "externalSeriesRule": "Normalize external series as returns, deltas, z-scores, release surprises, staleness, and missingness flags before ML use.",
        "trainingRule": "Train supervised models only on known labels; pending live markets stay unlabeled.",
    }
