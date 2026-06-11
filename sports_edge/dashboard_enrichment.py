from __future__ import annotations

from statistics import mean
from typing import Any

from .external_sources import build_external_data_readiness
from .research_scope import ACTIVE_CATEGORIES, AGENT_CONTRACT, category_label
from .source_registry import SourceRecord, SourceRegistry


SOURCE_URLS = {
    "polymarket-docs": "https://docs.polymarket.com/api-reference",
    "polymarket-gamma": "https://gamma-api.polymarket.com/markets",
    "polymarket-clob": "https://clob.polymarket.com/",
    "polymarket-data-api": "https://data-api.polymarket.com/",
    "polymarket-local-api-notes": "docs/POLYMARKET_API_NOTES.md",
    "global-gdelt-cloud": "https://docs.gdeltcloud.com/api-reference",
    "global-media-cloud": "https://www.mediacloud.org/documentation",
    "global-event-registry": "https://newsapi.ai/about",
    "global-newsapi": "https://newsapi.org/docs/endpoints",
    "global-official-press-rss": "https://www.usa.gov/agency-index",
    "global-sec-edgar-companyfacts": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    "global-wto-timeseries": "https://apiportal.wto.org/",
    "global-un-comtrade": "https://comtradeplus.un.org/",
    "sports-the-odds-api": "https://api.the-odds-api.com/",
    "sports-sportradar": "https://docs.sportradar.com/sports-data-api",
    "sports-sportsdataio": "https://sportsdata.io/developers/api-documentation",
    "sports-official-league-schedules": "https://www.nba.com/schedule",
    "sports-official-injury-reports": "https://official.nba.com/nba-injury-report-2024-25-season/",
    "sports-polymarket-sports-metadata": "https://polymarket.com/sports",
    "sports-official-league-standings-tables": "https://www.nba.com/standings",
    "sports-football-data-org": "https://docs.football-data.org/general/v4/index.html",
    "sports-openligadb": "https://openligadb.de/",
    "sports-mlb-stats-api": "https://statsapi.mlb.com/api/v1/schedule?sportId=1",
    "sports-nba-official-stats": "https://www.nba.com/stats",
    "sports-nhl-web-api": "https://api-web.nhle.com/v1/standings/now",
    "sports-official-nfl-stats": "https://www.nfl.com/stats/",
    "sports-balldontlie": "https://www.balldontlie.io/docs/",
    "sports-pandascore-esports": "https://developers.pandascore.co/docs",
    "sports-tennis-official-rankings-results": "https://www.atptour.com/en/rankings/singles",
    "sports-espn-unofficial": "https://site.api.espn.com/apis/site/v2/sports",
    "geopolitics-reliefweb": "https://apidoc.reliefweb.int/",
    "geopolitics-acled": "https://acleddata.com/acled-api-documentation",
    "geopolitics-un-press": "https://press.un.org/en",
    "geopolitics-nato-rss": "https://www.nato.int/cps/en/natohq/news.htm",
    "geopolitics-eu-council-press": "https://www.consilium.europa.eu/en/press/",
    "geopolitics-official-election-boards": "https://www.eac.gov/voters/register-and-vote-in-your-state",
    "geopolitics-gdelt": "https://docs.gdeltproject.org/",
    "geopolitics-ucdp-api": "https://ucdp.uu.se/apidocs/",
    "geopolitics-official-sanctions-lists": "https://ofac.treasury.gov/sanctions-list-service",
    "geopolitics-ofac-sanctions-list-service": "https://ofac.treasury.gov/sanctions-list-service",
    "geopolitics-congress-gov-api": "https://api.congress.gov/",
    "geopolitics-regulations-gov-api": "https://open.gsa.gov/api/regulationsgov/",
    "geopolitics-usaspending-api": "https://api.usaspending.gov/",
    "crypto-coingecko": "https://docs.coingecko.com/reference/endpoint-overview",
    "crypto-coinmetrics-community": "https://docs.coinmetrics.io/api",
    "crypto-defillama": "https://defillama.com/docs/api",
    "crypto-binance-public-market-data": "https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints",
    "crypto-coinbase-exchange-market-data": "https://docs.cdp.coinbase.com/exchange/introduction/welcome",
    "crypto-kraken-public-market-data": "https://docs.kraken.com/api/",
    "crypto-chainlink-market-data-feeds": "https://docs.chain.link/data-feeds",
    "crypto-deribit-public-market-data": "https://docs.deribit.com/",
    "crypto-okx-public-market-data": "https://www.okx.com/docs-v5/",
    "macro-fred": "https://fred.stlouisfed.org/docs/api/fred/",
    "macro-bls": "https://www.bls.gov/bls/api_features.htm",
    "macro-bea": "https://www.bea.gov/open-data",
    "macro-treasury-fiscaldata": "https://fiscaldata.treasury.gov/api-documentation/",
    "macro-eia": "https://www.eia.gov/opendata/documentation.php",
    "macro-world-bank": "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
    "macro-imf": "https://data.imf.org/en/Resource-Pages/IMF-API",
    "macro-oecd-data-api": "https://sdmx.oecd.org/public/rest/",
    "macro-eurostat-api": "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/api-statistics",
    "macro-wto-timeseries": "https://apiportal.wto.org/",
    "macro-ecb-data-portal": "https://data.ecb.europa.eu/help/api/data",
    "macro-census-international-trade": "https://www.census.gov/data/developers/data-sets/international-trade.html",
    "weather-nws-api": "https://www.weather.gov/documentation/services-web-api",
    "weather-noaa-cdo": "https://www.ncdc.noaa.gov/cdo-web/webservices/v2",
    "weather-nhc-rss-gis": "https://www.nhc.noaa.gov/gis/rss.php",
    "weather-ecmwf-open-data": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
    "weather-open-meteo": "https://open-meteo.com/en/docs",
    "weather-nasa-firms": "https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html",
    "weather-noaa-nwps": "https://water.noaa.gov/about/nwps",
    "culture-tmdb": "https://developer.themoviedb.org/docs/getting-started",
    "culture-wikimedia-pageviews": "https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageview_API",
    "culture-youtube-data-api": "https://developers.google.com/youtube/v3/docs",
    "culture-official-awards-sites": "https://www.oscars.org/oscars",
    "culture-official-platform-press": "https://www.netflix.com/tudum",
    "culture-box-office-mojo": "https://www.boxofficemojo.com/",
    "culture-the-numbers": "https://www.the-numbers.com/",
    "culture-steam-public-charts": "https://store.steampowered.com/charts",
}


def enrich_multi_agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    registry = SourceRegistry()
    recommendations = payload.get("recommendations", [])
    metrics = payload.get("metrics", {})
    payload["portfolio_rules"] = _portfolio_rules(metrics)
    payload["agent_contract"] = AGENT_CONTRACT
    payload["collection_plan"] = _collection_plan(registry)
    payload["source_reviews_by_category"] = _source_reviews_by_category(registry)
    payload["external_data_readiness"] = build_external_data_readiness(
        [item.get("candidate", {}) for item in recommendations],
        registry=registry,
        decision_at=payload.get("created_at", ""),
    )
    payload["event_groups"] = _event_groups(recommendations)
    payload["news_influence_graph"] = _news_influence_graph(recommendations)
    payload["bet_detail_records"] = [
        _bet_detail_record(item, metrics, registry, payload.get("created_at", "")) for item in recommendations
    ]
    _compact_dashboard_transport(payload)
    return payload


def source_url(source_id: str) -> str:
    return SOURCE_URLS.get(source_id, "")


def _compact_dashboard_transport(payload: dict[str, Any]) -> None:
    payload["candidate_index"] = [
        {
            "candidate_id": candidate["candidate_id"],
            "event_id": candidate["event_id"],
            "category": candidate["category"],
            "market_title": candidate["market_title"],
            "outcome": candidate["outcome"],
        }
        for candidate in payload.get("candidates", [])
    ]
    payload["candidates"] = []
    for item in payload.get("recommendations", []):
        _compact_recommendation(item)
    for key in ("top_bets", "paper_bets", "watchlist", "rejected"):
        payload[key] = [_compact_recommendation_copy(item) for item in payload.get(key, [])]


def _compact_recommendation(item: dict[str, Any]) -> None:
    for assessment in item.get("assessments", {}).values():
        features = assessment.get("features") or {}
        assessment["feature_keys"] = sorted(features.keys())
        assessment["features"] = {
            key: value
            for key, value in features.items()
            if isinstance(value, (int, float, str, bool)) and len(str(value)) <= 240
        }


def _compact_recommendation_copy(item: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "candidate": item["candidate"],
        "blended_probability": item["blended_probability"],
        "confidence": item["confidence"],
        "edge": item["edge"],
        "expected_value": item["expected_value"],
        "risk_tier": item["risk_tier"],
        "decision": item["decision"],
        "stake_units": item["stake_units"],
        "reason": item["reason"],
        "rank_score": item["rank_score"],
        "outcome": item.get("outcome"),
        "pnl_units": item.get("pnl_units", 0.0),
        "bankroll_after": item.get("bankroll_after"),
    }
    return compact


def _portfolio_rules(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "paper_only",
        "target_bankroll_units": 100.0,
        "simultaneous_allocation_rule": "Allocate the full 100-coin paper bankroll across qualified simultaneous bets.",
        "staked_units": round(float(metrics.get("total_staked_units", 0.0)), 4),
        "available_units": round(float(metrics.get("unallocated_budget_units", 0.0)), 4),
        "safety_boundary": "No wallet, credentials, order posting, or automated real-money betting.",
        "risk_controls": [
            "Rank by calibrated EV, confidence, liquidity, spread, source reliability, contradiction risk, and resolution ambiguity.",
            "Cap exposure by event, category, risk tier, and settlement ambiguity.",
            "Keep rejected and watchlist markets visible for monitoring, but allocate stake only to PAPER_BET records.",
            "Fixture mode is deterministic by default; live public API mode remains read-only and opt-in.",
        ],
    }


def _collection_plan(registry: SourceRegistry) -> dict[str, Any]:
    rows = []
    for source in registry.active_sources():
        scripted = source.allowed_by_default and source.access == "public-no-key"
        rows.append(
            {
                **source.to_dict(),
                "url": source_url(source.id),
                "scripted": scripted,
                "fixture_mode": True,
                "live_fetch": False,
                "refresh_seconds": 900 if scripted else None,
                "status": "scripted_fixture_ready" if scripted else "planned_requires_access_or_license_review",
            }
        )
    return {
        "mode": "fixture_default_public_api_plan",
        "refresh_seconds": 900,
        "live_fetch_default": False,
        "public_api_count": sum(1 for row in rows if row["scripted"]),
        "planned_source_count": len(rows),
        "rows": rows,
    }


def _source_reviews_by_category(registry: SourceRegistry) -> dict[str, list[dict[str, Any]]]:
    return {
        category: [
            {
                **source.to_dict(),
                "url": source_url(source.id),
                "used_by_agents": _source_agents(source),
                "review_status": "fixture_query_scripted" if source.allowed_by_default else "visible_not_enabled_by_default",
                "live_fetch": False,
            }
            for source in registry.for_category(category, include_global=True, include_polymarket=True, allowed_only=False)[:14]
        ]
        for category in ACTIVE_CATEGORIES
    }


def _event_groups(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in recommendations:
        groups.setdefault(str(item["candidate"]["event_id"]), []).append(item)
    rows = []
    for event_id, items in groups.items():
        first = items[0]["candidate"]
        sub_bets = [
            {
                "candidate_id": item["candidate"]["candidate_id"],
                "market_title": item["candidate"]["market_title"],
                "outcome": item["candidate"]["outcome"],
                "decision": item["decision"],
                "state": _state(item)["state"],
                "probability": item["blended_probability"],
                "expected_value": item["expected_value"],
                "stake_units": item["stake_units"],
                "risk_tier": item["risk_tier"],
            }
            for item in sorted(items, key=lambda row: row["rank_score"], reverse=True)
        ]
        rows.append(
            {
                "event_id": event_id,
                "category": first["category"],
                "subcategory": first["subcategory"],
                "event_title": _event_title(first),
                "sub_bet_count": len(sub_bets),
                "paper_bet_count": sum(1 for item in items if item["decision"] == "PAPER_BET"),
                "total_stake_units": round(sum(float(item["stake_units"]) for item in items), 4),
                "best_rank_score": max(float(item["rank_score"]) for item in items),
                "sub_bets": sub_bets,
            }
        )
    return sorted(rows, key=lambda row: (row["total_stake_units"], row["best_rank_score"]), reverse=True)


def _news_influence_graph(recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges = []
    for item in recommendations:
        candidate = item["candidate"]
        for news in candidate.get("news_items", []):
            source = str(news.get("source", "unknown"))
            node_id = f"news:{source}"
            impact = float(news.get("impact", 0.0))
            credibility = float(news.get("credibility", 0.5))
            node = nodes.setdefault(
                node_id,
                {
                    "id": node_id,
                    "source": source,
                    "headline": news.get("headline", ""),
                    "affected_count": 0,
                    "net_impact": 0.0,
                    "avg_credibility": [],
                    "top_bets": [],
                },
            )
            node["affected_count"] += 1
            node["net_impact"] = round(float(node["net_impact"]) + impact * credibility, 4)
            node["avg_credibility"].append(credibility)
            node["top_bets"].append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "market_title": candidate["market_title"],
                    "decision": item["decision"],
                    "state": _state(item)["state"],
                    "impact": impact,
                    "expected_value": item["expected_value"],
                }
            )
            edges.append(
                {
                    "from": node_id,
                    "to": candidate["candidate_id"],
                    "direction": "up" if impact >= 0 else "down",
                    "weight": round(abs(impact) * credibility, 4),
                    "explanation": news.get("headline", ""),
                }
            )
    node_rows = []
    for node in nodes.values():
        node["avg_credibility"] = round(mean(node["avg_credibility"]), 4) if node["avg_credibility"] else 0.0
        node["top_bets"] = sorted(node["top_bets"], key=lambda row: abs(float(row["impact"])), reverse=True)[:8]
        node["direction"] = "up" if float(node["net_impact"]) >= 0 else "down"
        node["conclusion"] = _news_conclusion(node)
        node_rows.append(node)
    return {
        "nodes": sorted(node_rows, key=lambda row: abs(float(row["net_impact"])), reverse=True),
        "edges": sorted(edges, key=lambda row: row["weight"], reverse=True)[:240],
    }


def _bet_detail_record(item: dict[str, Any], metrics: dict[str, Any], registry: SourceRegistry, run_created_at: str) -> dict[str, Any]:
    candidate = item["candidate"]
    state = _state(item)
    history = _history_summary(candidate.get("odds_history", []))
    source_reviews = _source_reviews(item, registry)
    monitored_values = _monitored_values(item, history)
    return {
        "candidate_id": candidate["candidate_id"],
        "state": state["state"],
        "state_label": state["label"],
        "state_explanation": state["explanation"],
        "decision_made_at": run_created_at,
        "market_url": candidate.get("source_url", ""),
        "history_summary": history,
        "forecast_summary": _forecast_summary(item, history),
        "source_review_ids": [source["id"] for source in source_reviews],
        "source_queries": [{"source_id": source["id"], "query": source["query"]} for source in source_reviews[:3]],
        "model_cards": _compact_model_cards(item, history),
        "monitored_values": monitored_values,
        "decision_steps": _decision_steps(item, source_reviews, monitored_values, history, run_created_at),
        "portfolio_effect": _portfolio_effect(item, metrics),
        "event_relation": {
            "event_id": candidate["event_id"],
            "event_title": _event_title(candidate),
            "subcategory": candidate["subcategory"],
        },
        "news_motivation": _news_motivation(candidate.get("news_items", [])),
    }


def _source_reviews(item: dict[str, Any], registry: SourceRegistry) -> list[dict[str, Any]]:
    candidate = item["candidate"]
    topic = candidate["market_title"]
    sources = registry.search(topic, category=candidate["category"], allowed_only=False, limit=14)
    return [
        {
            **source.to_dict(),
            "url": source_url(source.id),
            "query": registry.render_query(source, topic=topic, actors=", ".join(candidate.get("actors", [])), category=candidate["category"]),
            "used_by_agents": _source_agents(source),
            "review_status": "fixture_query_scripted" if source.allowed_by_default else "visible_not_enabled_by_default",
            "live_fetch": False,
        }
        for source in sources
    ]


def _source_agents(source: SourceRecord) -> list[str]:
    agents = ["market_context_news"]
    if "polymarket" in source.category or "market" in source.source_type:
        agents.append("odds_modeling")
    if source.category not in {"global", "polymarket"}:
        agents.append("category_expert")
    if source.reliability_tier in {"primary", "high"}:
        agents.append("decision_bankroll")
    return agents


def _decision_steps(
    item: dict[str, Any],
    source_reviews: list[dict[str, Any]],
    monitored_values: list[dict[str, Any]],
    history: dict[str, Any],
    run_created_at: str,
) -> list[dict[str, Any]]:
    candidate = item["candidate"]
    news_items = candidate.get("news_items", [])
    return [
        {
            "step": 1,
            "title": "Public API and fixture-source collection",
            "status": "complete",
            "motivation": "Use official/public read-only sources first, keep paid/keyed sources visible but disabled until access review.",
            "evidence": [review["name"] for review in source_reviews[:4]],
            "links": [],
        },
        {
            "step": 2,
            "title": "Historical market path",
            "status": "complete",
            "motivation": f"Previous price moved {history['direction']} from {history['first_price']:.1%} to {history['latest_price']:.1%}; trend is checked before EV.",
            "evidence": {},
            "links": [{"label": "Market", "url": candidate.get("source_url", "")}] if candidate.get("source_url", "").startswith("http") else [],
        },
        {
            "step": 3,
            "title": "News and context motivation",
            "status": "complete" if news_items else "blocked",
            "motivation": _news_motivation(news_items),
            "evidence": [],
            "links": [],
        },
        {
            "step": 4,
            "title": "Model probability review",
            "status": "complete",
            "motivation": "Odds model, context agent, and category expert are blended into the final probability.",
            "evidence": {},
            "links": [],
        },
        {
            "step": 5,
            "title": "Decision and 100-coin portfolio allocation",
            "status": "complete" if item["decision"] == "PAPER_BET" else "monitor",
            "motivation": f"{item['decision']} at {item['stake_units']:.2f} paper coins because {item['reason']}.",
            "evidence": {},
            "links": [],
        },
        {
            "step": 6,
            "title": "Monitoring triggers",
            "status": "monitor",
            "motivation": "Keep watching the values that can invalidate the thesis before settlement.",
            "evidence": [],
            "links": [],
        },
        {
            "step": 7,
            "title": "Outcome and learning",
            "status": _state(item)["state"],
            "motivation": f"Current simulated state is {_state(item)['label']}; settled fixture results are used only for model learning.",
            "evidence": {},
            "links": [],
        },
    ]


def _model_cards(item: dict[str, Any], history: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for key, assessment in item["assessments"].items():
        cards.append(
            {
                "agent": key,
                "probability": assessment["probability"],
                "confidence": assessment["confidence"],
                "score": assessment["score"],
                "rationale": assessment["rationale"],
                "features": assessment.get("features", {}),
                "flags": assessment.get("flags", []),
            }
        )
    cards.append(
        {
            "agent": "forecast_blend",
            "probability": item["blended_probability"],
            "confidence": item["confidence"],
            "score": item["rank_score"],
            "rationale": "Blended probability combines odds modeling, news context, category rules, then applies portfolio and resolution risk penalties.",
            "features": {
                "expected_value": item["expected_value"],
                "edge": item["edge"],
                "price_trend_direction": history["direction"],
                "history_volatility": history["volatility"],
            },
            "flags": item["candidate"].get("contradiction_flags", [])
            + item["candidate"].get("staleness_flags", [])
            + item["candidate"].get("resolution_risk_flags", []),
        }
    )
    return cards


def _compact_model_cards(item: dict[str, Any], history: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [
        {
            "agent": key,
            "probability": assessment["probability"],
            "confidence": assessment["confidence"],
            "score": assessment["score"],
            "feature_keys": sorted((assessment.get("features") or {}).keys()),
            "flags": assessment.get("flags", []),
        }
        for key, assessment in item["assessments"].items()
    ]
    cards.append(
        {
            "agent": "forecast_blend",
            "probability": item["blended_probability"],
            "confidence": item["confidence"],
            "score": item["rank_score"],
            "feature_keys": ["expected_value", "edge", "price_trend_direction", "history_volatility"],
            "flags": item["candidate"].get("contradiction_flags", [])
            + item["candidate"].get("staleness_flags", [])
            + item["candidate"].get("resolution_risk_flags", []),
            "summary_features": {
                "expected_value": item["expected_value"],
                "edge": item["edge"],
                "price_trend_direction": history["direction"],
                "history_volatility": history["volatility"],
            },
        }
    )
    return cards


def _monitored_values(item: dict[str, Any], history: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = item["candidate"]
    return [
        {"name": "Blended probability", "value": item["blended_probability"], "format": "percent"},
        {"name": "Market price", "value": candidate["price"], "format": "percent"},
        {"name": "Expected value", "value": item["expected_value"], "format": "signed_percent"},
        {"name": "Spread", "value": candidate["spread"], "format": "percent"},
        {"name": "Liquidity", "value": candidate["liquidity"], "format": "coins"},
        {"name": "Volume 24h", "value": candidate["volume_24h"], "format": "coins"},
        {"name": "Trend slope", "value": history["slope"], "format": "number"},
        {"name": "Resolution ambiguity", "value": candidate["stats"].get("ambiguity", 0.0), "format": "percent"},
        {"name": "Bet research score", "value": candidate.get("bet_research_score", 0.0), "format": "percent"},
    ]


def _forecast_summary(item: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    confidence = float(item["confidence"])
    probability = float(item["blended_probability"])
    uncertainty = max(0.04, (1.0 - confidence) * 0.16 + float(item["candidate"]["spread"]))
    return {
        "forecast_probability": round(probability, 4),
        "lower_bound": round(max(probability - uncertainty, 0.01), 4),
        "upper_bound": round(min(probability + uncertainty, 0.99), 4),
        "horizon": "until market settlement window",
        "trend_direction": history["direction"],
        "decision_rule": "Paper bet only when edge, EV, liquidity, source reliability, and resolution-risk controls pass.",
    }


def _portfolio_effect(item: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    stake = float(item.get("stake_units", 0.0))
    budget = float(metrics.get("deployment_budget_units", 100.0))
    total_staked = float(metrics.get("total_staked_units", 0.0))
    return {
        "stake_units": round(stake, 4),
        "portfolio_share": round(stake / budget, 4) if budget else 0.0,
        "total_staked_units": round(total_staked, 4),
        "available_units": round(float(metrics.get("unallocated_budget_units", 0.0)), 4),
        "paper_bankroll_units": budget,
        "balance_after_simulated_settlement": item.get("bankroll_after"),
    }


def _history_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [float(point.get("price", 0.0)) for point in history]
    if not prices:
        return {"first_price": 0.0, "latest_price": 0.0, "min_price": 0.0, "max_price": 0.0, "slope": 0.0, "volatility": 0.0, "direction": "flat"}
    slope = (prices[-1] - prices[0]) / max(len(prices) - 1, 1)
    avg = mean(prices)
    volatility = mean([abs(price - avg) for price in prices]) if len(prices) > 1 else 0.0
    if slope > 0.002:
        direction = "up"
    elif slope < -0.002:
        direction = "down"
    else:
        direction = "flat"
    return {
        "first_price": round(prices[0], 4),
        "latest_price": round(prices[-1], 4),
        "min_price": round(min(prices), 4),
        "max_price": round(max(prices), 4),
        "slope": round(slope, 5),
        "volatility": round(volatility, 5),
        "direction": direction,
    }


def _state(item: dict[str, Any]) -> dict[str, str]:
    decision = item.get("decision")
    outcome = item.get("outcome")
    if decision == "PAPER_BET" and outcome == "WIN":
        return {"state": "win", "label": "Won paper bet", "explanation": "Fixture-settled paper bet produced positive simulated PnL."}
    if decision == "PAPER_BET" and outcome == "LOSS":
        return {"state": "loss", "label": "Lost paper bet", "explanation": "Fixture-settled paper bet produced negative simulated PnL."}
    if decision == "PAPER_BET":
        return {"state": "betted", "label": "Paper bet active", "explanation": "Accepted into the simultaneous 100-coin paper portfolio."}
    if decision == "WATCHLIST":
        return {"state": "monitoring", "label": "Monitoring", "explanation": "Edge exists but one or more reliability controls blocks allocation."}
    if decision == "REJECTED":
        return {"state": "rejected", "label": "Rejected", "explanation": "Category, liquidity, spread, or resolution rule rejected it."}
    return {"state": "planning", "label": "No bet / planning", "explanation": "Visible for review but not allocated."}


def _news_motivation(news_items: list[dict[str, Any]]) -> str:
    if not news_items:
        return "No fixture-backed news items are attached; source collection must run before confidence can improve."
    strongest = max(news_items, key=lambda row: abs(float(row.get("impact", 0.0))) * float(row.get("credibility", 0.5)))
    direction = "supports" if float(strongest.get("impact", 0.0)) >= 0 else "weakens"
    return f"{strongest.get('source', 'source')} {direction} the Yes case: {strongest.get('headline', '')}"


def _news_conclusion(node: dict[str, Any]) -> str:
    direction = "raises" if float(node["net_impact"]) >= 0 else "lowers"
    return f"{node['source']} currently {direction} related bet probabilities across {node['affected_count']} reviewed records."


def _event_title(candidate: dict[str, Any]) -> str:
    return f"{candidate['category']} / {candidate['subcategory']} / {candidate['event_id']}"
