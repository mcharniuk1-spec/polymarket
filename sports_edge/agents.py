from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any

from .odds_math import clamp
from .polymarket_client import PolymarketClientError, PolymarketPublicClient, parse_polymarket_list
from .research_scope import ACTIVE_CATEGORIES, AGENT_CONTRACT, category_label, normalize_category_id


PAPER_MODE = "paper"


@dataclass(frozen=True)
class MarketCandidate:
    candidate_id: str
    event_id: str
    category: str
    subcategory: str
    market_title: str
    outcome: str
    price: float
    spread: float
    liquidity: float
    volume_24h: float
    end_time: str
    source: str
    source_url: str
    actors: list[str]
    news_items: list[dict[str, Any]]
    stats: dict[str, float]
    odds_history: list[dict[str, Any]]
    resolution_notes: str
    resolved_outcome: int | None = None
    published_at: str = ""
    updated_at: str = ""
    token_id: str = ""

    @property
    def decimal_odds(self) -> float:
        return round(1.0 / max(self.price, 0.01), 4)

    def context_fields(self) -> dict[str, Any]:
        impacts = [float(item.get("impact", 0.0)) for item in self.news_items]
        credibilities = [float(item.get("credibility", 0.5)) for item in self.news_items]
        unique_sources = {str(item.get("source", "unknown")) for item in self.news_items}
        source_depth = float(self.stats.get("source_depth", 0.0))
        ambiguity = float(self.stats.get("ambiguity", 0.25))
        avg_credibility = mean(credibilities) if credibilities else 0.0
        avg_abs_impact = mean([abs(value) for value in impacts]) if impacts else 0.0
        positive = any(value > 0.02 for value in impacts)
        negative = any(value < -0.02 for value in impacts)
        contradiction_flags = ["mixed_direction_news"] if positive and negative else []
        staleness_flags = []
        if self.source == "fixture":
            staleness_flags.append("fixture_context_not_live")
        if not self.news_items:
            staleness_flags.append("no_news_items")
        resolution_text = f"{self.resolution_notes} {self.market_title}".lower()
        resolution_risk_flags = []
        if ambiguity > 0.35:
            resolution_risk_flags.append("resolution_ambiguity")
        if any(word in resolution_text for word in ("depends", "requires", "subjective", "verify", "deadline")):
            resolution_risk_flags.append("settlement_wording_review")
        if self.category == "politics" and ambiguity > 0.25:
            resolution_risk_flags.append("category_wording_sensitive")
        global_context_score = clamp(
            (source_depth * 0.42) + (avg_credibility * 0.38) + (clamp(len(unique_sources) / 5.0, 0.0, 1.0) * 0.20),
            0.0,
            1.0,
        )
        category_context_score = clamp(
            ((1.0 - ambiguity) * 0.34) + (source_depth * 0.28) + (avg_abs_impact * 0.38),
            0.0,
            1.0,
        )
        bet_research_score = clamp(
            ((global_context_score + category_context_score) / 2.0)
            - (len(contradiction_flags) * 0.08)
            - (len(resolution_risk_flags) * 0.04),
            0.0,
            1.0,
        )
        return {
            "global_context_score": round(global_context_score, 4),
            "category_context_score": round(category_context_score, 4),
            "bet_research_score": round(bet_research_score, 4),
            "source_coverage": {
                "news_item_count": len(self.news_items),
                "unique_news_source_count": len(unique_sources),
                "source_depth": round(source_depth, 4),
                "fixture_backed": self.source == "fixture",
            },
            "contradiction_flags": contradiction_flags,
            "staleness_flags": staleness_flags,
            "resolution_risk_flags": resolution_risk_flags,
        }

    def to_dict(self) -> dict[str, Any]:
        context_fields = self.context_fields()
        return {
            "candidate_id": self.candidate_id,
            "event_id": self.event_id,
            "category": self.category,
            "subcategory": self.subcategory,
            "market_title": self.market_title,
            "outcome": self.outcome,
            "price": self.price,
            "market_probability": self.price,
            "decimal_odds": self.decimal_odds,
            "spread": self.spread,
            "liquidity": self.liquidity,
            "volume_24h": self.volume_24h,
            "end_time": self.end_time,
            "published_at": self.published_at,
            "updated_at": self.updated_at,
            "token_id": self.token_id,
            "source": self.source,
            "source_url": self.source_url,
            "actors": self.actors,
            "news_items": self.news_items,
            "stats": self.stats,
            "odds_history": self.odds_history,
            "resolution_notes": self.resolution_notes,
            "resolved_outcome": self.resolved_outcome,
            "global_context_score": context_fields["global_context_score"],
            "category_context_score": context_fields["category_context_score"],
            "bet_research_score": context_fields["bet_research_score"],
            "source_coverage": context_fields["source_coverage"],
            "contradiction_flags": context_fields["contradiction_flags"],
            "staleness_flags": context_fields["staleness_flags"],
            "resolution_risk_flags": context_fields["resolution_risk_flags"],
        }


@dataclass(frozen=True)
class AgentAssessment:
    agent: str
    probability: float
    confidence: float
    score: float
    rationale: str
    features: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "probability": self.probability,
            "confidence": self.confidence,
            "score": self.score,
            "rationale": self.rationale,
            "features": self.features,
            "flags": self.flags,
        }


@dataclass(frozen=True)
class MultiAgentRun:
    run_id: str
    created_at: str
    mode: str
    source_mode: str
    source_note: str
    candidates: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    paper_bets: list[dict[str, Any]]
    watchlist: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    top_bets: list[dict[str, Any]]
    category_stats: list[dict[str, Any]]
    agent_performance: list[dict[str, Any]]
    metrics: dict[str, Any]
    bankroll_curve: list[dict[str, Any]]
    mistakes: list[dict[str, Any]]
    agent_contract: dict[str, Any] = field(default_factory=lambda: AGENT_CONTRACT.copy())

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def logit(probability: float) -> float:
    p = clamp(probability, 0.001, 0.999)
    return math.log(p / (1.0 - p))


def logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def simple_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    xs = list(range(len(values)))
    x_bar = mean(xs)
    y_bar = mean(values)
    denominator = sum((x - x_bar) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, values)) / denominator


class MarketDataAgent:
    def __init__(self, client: PolymarketPublicClient | None = None) -> None:
        self.client = client or PolymarketPublicClient()
        self.source_note = "bundled deterministic multi-category fixture"

    def load_candidates(self, source_mode: str = "fixture", target_count: int = 300) -> list[MarketCandidate]:
        if source_mode == "live":
            try:
                candidates = self._load_live_candidates(target_count)
            except PolymarketClientError as exc:
                return self._fixture_candidates(
                    target_count,
                    source_note=f"live Polymarket public API unavailable; fixture fallback used: {exc}",
                )
            if candidates:
                self.source_note = f"live Gamma API market discovery returned {len(candidates)} candidate outcomes"
                return candidates
            return self._fixture_candidates(
                target_count,
                source_note="live Gamma API returned no usable outcomes; fixture fallback used",
            )
        return self._fixture_candidates(target_count)

    def _load_live_candidates(self, target_count: int) -> list[MarketCandidate]:
        markets: list[dict[str, Any]] = []
        offset = 0
        while len(markets) < target_count:
            limit = min(max(target_count - len(markets), 100), 500)
            batch = self.client.fetch_gamma_markets(limit=limit, offset=offset, order="createdAt")
            if not batch:
                break
            markets.extend(batch)
            offset += len(batch)
            if len(batch) < limit:
                break
        candidates: list[MarketCandidate] = []
        for market in markets:
            outcomes = parse_polymarket_list(market.get("outcomes"))
            prices = parse_polymarket_list(market.get("outcomePrices") or market.get("outcome_prices"))
            token_ids = parse_polymarket_list(market.get("clobTokenIds") or market.get("clob_token_ids"))
            if not outcomes or not prices:
                continue
            for idx, outcome in enumerate(outcomes):
                try:
                    price = float(prices[idx])
                except (IndexError, TypeError, ValueError):
                    continue
                if not 0.02 <= price <= 0.98:
                    continue
                question = str(market.get("question") or market.get("title") or "Polymarket market")
                category = self._normalize_category(str(market.get("category") or market.get("tags") or question))
                if category is None:
                    continue
                token_id = str(token_ids[idx]) if idx < len(token_ids) else ""
                spread = self._spread_from_market(market, token_id)
                history = self._history_from_price(price, idx + len(candidates), live=True)
                published_at = str(market.get("createdAt") or market.get("startDate") or market.get("updatedAt") or "")
                updated_at = str(market.get("updatedAt") or published_at)
                stable_market_id = self._stable_live_candidate_id(market, idx, token_id, str(outcome))
                candidates.append(
                    MarketCandidate(
                        candidate_id=stable_market_id,
                        event_id=str(market.get("conditionId") or market.get("id") or f"live-{len(candidates)}"),
                        category=category,
                        subcategory=str(market.get("groupItemTitle") or market.get("marketType") or "polymarket"),
                        market_title=question,
                        outcome=str(outcome),
                        price=round(price, 4),
                        spread=spread,
                        liquidity=float(market.get("liquidity") or market.get("liquidityNum") or 0.0),
                        volume_24h=float(market.get("volume24hr") or market.get("volume24hrClob") or market.get("volume") or 0.0),
                        end_time=str(market.get("endDate") or market.get("end_date") or ""),
                        source="polymarket-gamma",
                        source_url=self._polymarket_url(market),
                        actors=self._actors_from_question(question),
                        news_items=self._news_stub_from_market(market),
                        stats=self._live_stats_stub(price, market),
                        odds_history=history,
                        resolution_notes=str(market.get("resolutionSource") or market.get("description") or "Review Polymarket market rules before action.")[:280],
                        resolved_outcome=None,
                        published_at=published_at,
                        updated_at=updated_at,
                        token_id=token_id,
                    )
                )
                if len(candidates) >= target_count:
                    return self._newest_first(candidates)
        return self._newest_first(candidates)

    @staticmethod
    def _stable_live_candidate_id(market: dict[str, Any], outcome_index: int, token_id: str, outcome: str) -> str:
        slug = str(market.get("slug") or market.get("marketSlug") or market.get("id") or "market")
        token_part = token_id or str(market.get("conditionId") or outcome_index)
        digest = hashlib.sha1(f"{slug}:{token_part}:{outcome}".encode("utf-8")).hexdigest()[:10]
        return f"live-{slug}-{outcome_index}-{digest}"

    @staticmethod
    def _newest_first(candidates: list[MarketCandidate]) -> list[MarketCandidate]:
        return sorted(
            candidates,
            key=lambda row: row.published_at or row.updated_at or row.end_time or "",
            reverse=True,
        )

    def _spread_from_book(self, token_id: str) -> float:
        if not token_id:
            return 0.04
        try:
            book = self.client.fetch_order_book(token_id)
        except PolymarketClientError:
            return 0.04
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        try:
            best_bid = max(float(item.get("price", 0.0)) for item in bids)
            best_ask = min(float(item.get("price", 1.0)) for item in asks)
        except (TypeError, ValueError):
            return 0.04
        return round(max(best_ask - best_bid, 0.0), 4)

    def _spread_from_market(self, market: dict[str, Any], token_id: str) -> float:
        try:
            spread = float(market.get("spread"))
            if spread >= 0:
                return round(spread, 4)
        except (TypeError, ValueError):
            pass
        try:
            best_bid = float(market.get("bestBid"))
            best_ask = float(market.get("bestAsk"))
            if best_ask >= best_bid:
                return round(best_ask - best_bid, 4)
        except (TypeError, ValueError):
            pass
        return self._spread_from_book(token_id)

    @staticmethod
    def _polymarket_url(market: dict[str, Any]) -> str:
        slug = market.get("slug") or market.get("marketSlug")
        return f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"

    @staticmethod
    def _normalize_category(raw: str) -> str | None:
        lowered = raw.lower()
        words = set(re.findall(r"[a-z0-9]+", lowered))
        if normalized := normalize_category_id(lowered):
            return normalized
        sports_phrases = (
            "league of legends",
            "counter strike",
            "counter-strike",
            "j league",
            "j2 league",
            "premier league",
            "champions league",
            "t20 blast",
            "pro a",
        )
        if words & {
            "nba",
            "wnba",
            "nfl",
            "mlb",
            "nhl",
            "sports",
            "soccer",
            "football",
            "tennis",
            "atp",
            "wta",
            "itf",
            "ufc",
            "mma",
            "cricket",
            "basketball",
            "bbl",
            "lnb",
            "bsl",
            "euroleague",
            "eurocup",
            "esports",
            "dota",
            "valorant",
            "cs2",
        } or any(phrase in lowered for phrase in sports_phrases):
            return None
        if words & {"weather", "hurricane", "temperature", "rain", "snow", "storm", "wind", "precipitation", "wildfire"}:
            return None
        if words & {
            "fed",
            "inflation",
            "economy",
            "economic",
            "finance",
            "macro",
            "cpi",
            "jobs",
            "treasury",
            "gdp",
            "rates",
            "spy",
            "wti",
            "oil",
            "gold",
            "aapl",
            "msft",
            "tsla",
            "meta",
            "amzn",
            "nvda",
            "googl",
            "google",
            "alphabet",
        }:
            if words & {"spy", "aapl", "msft", "tsla", "meta", "amzn", "nvda", "googl", "google", "alphabet"}:
                return "stocks_trade"
            return "macroeconomics"
        if words & {
            "election",
            "elections",
            "politic",
            "politics",
            "geopolitic",
            "geopolitics",
            "war",
            "ceasefire",
            "sanctions",
            "ukraine",
            "israel",
            "china",
            "trump",
            "biden",
            "nato",
        }:
            return "politics"
        if words & {"stock", "stocks", "trade", "tariff", "tariffs", "sec", "nasdaq", "s&p", "sp500", "earnings"}:
            return "stocks_trade"
        return None

    @staticmethod
    def _actors_from_question(question: str) -> list[str]:
        words = [word.strip("?,.():;") for word in question.split()]
        actors = [word for word in words if word[:1].isupper() and len(word) > 2]
        return actors[:6] or ["Market participants"]

    @staticmethod
    def _news_stub_from_market(market: dict[str, Any]) -> list[dict[str, Any]]:
        updated = str(market.get("updatedAt") or market.get("createdAt") or "")
        return [
            {
                "time": updated,
                "source": "polymarket-market-metadata",
                "headline": str(market.get("description") or market.get("question") or "Market metadata reviewed")[:180],
                "impact": 0.0,
                "credibility": 0.55,
            }
        ]

    @staticmethod
    def _live_stats_stub(price: float, market: dict[str, Any]) -> dict[str, float]:
        liquidity = float(market.get("liquidity") or market.get("liquidityNum") or 0.0)
        volume = float(market.get("volume24hr") or market.get("volume") or 0.0)
        return {
            "actor_strength": clamp((price - 0.5) * 2.0, -1.0, 1.0),
            "source_depth": clamp(len(str(market.get("description") or "")) / 900.0, 0.0, 1.0),
            "liquidity_depth": clamp(liquidity / 50000.0, 0.0, 1.0),
            "volume_shock": clamp(volume / 25000.0, 0.0, 1.0),
            "ambiguity": 0.35 if len(str(market.get("description") or "")) < 80 else 0.15,
        }

    def _fixture_candidates(self, target_count: int, source_note: str | None = None) -> list[MarketCandidate]:
        self.source_note = source_note or "bundled deterministic fixture for macroeconomics, politics, and stocks/trade"
        rng = random.Random(20260525)
        templates = {
            "macroeconomics": ("Fed decision", "CPI", "unemployment", "oil", "treasury yields", "GDP"),
            "politics": ("US election", "EU sanctions", "Middle East ceasefire", "Taiwan policy", "congressional vote"),
            "stocks_trade": ("NVDA close", "S&P 500", "tariff deadline", "SEC filing", "oil equities", "trade data"),
        }
        actor_pool = {
            "macroeconomics": ("Federal Reserve", "BLS", "Treasury", "OPEC", "ECB", "BEA"),
            "politics": ("White House", "NATO", "EU Council", "Congress", "UN", "Election boards"),
            "stocks_trade": ("SEC", "Nasdaq", "USTR", "WTO", "UN Comtrade", "listed companies"),
        }
        candidates: list[MarketCandidate] = []
        per_category = max(18, math.ceil(target_count / len(ACTIVE_CATEGORIES)))
        base_time = now_utc()
        for category in ACTIVE_CATEGORIES:
            for idx in range(per_category):
                if len(candidates) >= target_count:
                    return candidates
                subcategory = templates[category][idx % len(templates[category])]
                price = clamp(0.18 + (((idx * 17) + (len(category) * 5)) % 64) / 100.0, 0.08, 0.91)
                spread = round(0.012 + ((idx * 3 + len(category)) % 8) / 1000.0 + (0.02 if category == "politics" and idx % 5 == 0 else 0.0), 4)
                liquidity = float(2500 + ((idx * 931 + len(category) * 701) % 90000))
                volume = float(500 + ((idx * 571 + len(subcategory) * 331) % 40000))
                context_tilt = (((idx * 11 + len(subcategory)) % 19) - 9) / 100.0
                trend_tilt = (((idx * 7 + len(category)) % 15) - 7) / 120.0
                latent_probability = clamp(price + context_tilt + trend_tilt, 0.03, 0.97)
                resolved = 1 if rng.random() < latent_probability else 0
                candidate_id = f"fixture-{category}-{idx:03d}"
                actors = list(actor_pool[category][: 2 + (idx % 3)])
                title = self._fixture_title(category, subcategory, idx, actors)
                candidates.append(
                    MarketCandidate(
                        candidate_id=candidate_id,
                        event_id=f"{category.upper()}-{idx // 2:03d}",
                        category=category,
                        subcategory=subcategory,
                        market_title=title,
                        outcome="Yes",
                        price=round(price, 4),
                        spread=spread,
                        liquidity=liquidity,
                        volume_24h=volume,
                        end_time=iso_z(base_time + timedelta(days=1 + (idx % 21))),
                        source="fixture",
                        source_url="local-fixture://polymarket",
                        actors=actors,
                        news_items=self._fixture_news(category, actors, idx, context_tilt),
                        stats=self._fixture_stats(category, idx, context_tilt),
                        odds_history=self._history_from_price(price, idx, live=False),
                        resolution_notes=self._fixture_resolution(category),
                        resolved_outcome=resolved,
                        published_at=iso_z(base_time - timedelta(minutes=idx + len(candidates))),
                        updated_at=iso_z(base_time),
                    )
                )
        return candidates

    @staticmethod
    def _fixture_title(category: str, subcategory: str, idx: int, actors: list[str]) -> str:
        if category == "politics":
            return f"Will {subcategory} produce a verified policy breakthrough before deadline #{idx + 1}?"
        if category == "macroeconomics":
            return f"Will {subcategory} resolve above consensus in release window #{idx + 1}?"
        return f"Will {subcategory} meet the market threshold before the trade window #{idx + 1}?"

    @staticmethod
    def _fixture_news(category: str, actors: list[str], idx: int, context_tilt: float) -> list[dict[str, Any]]:
        credibility = 0.62 + ((idx % 5) * 0.06)
        impact = clamp(abs(context_tilt) + 0.18 + (idx % 4) * 0.04, 0.05, 0.82)
        direction = "supports" if context_tilt >= 0 else "weakens"
        return [
            {
                "time": iso_z(now_utc() - timedelta(hours=idx + 2)),
                "source": f"{category}-source-{1 + idx % 3}",
                "headline": f"{actors[0]} update {direction} the Yes case; connected actors reviewed",
                "impact": round(context_tilt, 4),
                "credibility": round(credibility, 3),
            },
            {
                "time": iso_z(now_utc() - timedelta(hours=idx + 8)),
                "source": f"{category}-statistics-desk",
                "headline": f"Background indicators show {impact:.0%} contextual relevance for this market",
                "impact": round(context_tilt * 0.55, 4),
                "credibility": round(max(0.45, credibility - 0.12), 3),
            },
        ]

    @staticmethod
    def _fixture_stats(category: str, idx: int, context_tilt: float) -> dict[str, float]:
        return {
            "actor_strength": round(clamp(context_tilt * 3.2 + ((idx % 6) - 2.5) / 10.0, -1.0, 1.0), 4),
            "source_depth": round(clamp(0.35 + (idx % 8) / 12.0, 0.0, 1.0), 4),
            "liquidity_depth": round(clamp(0.20 + (idx % 10) / 10.0, 0.0, 1.0), 4),
            "volume_shock": round(clamp((idx % 9) / 8.0, 0.0, 1.0), 4),
            "ambiguity": round(0.12 + (0.18 if category == "politics" else 0.06) + ((idx % 4) * 0.025), 4),
        }

    @staticmethod
    def _fixture_resolution(category: str) -> str:
        if category == "politics":
            return "Requires verified official/public-source settlement; ambiguity risk is materially higher."
        if category == "macroeconomics":
            return "Economic-release settlement should use named official release and revision policy."
        return "Stocks/trade settlement depends on named market, official data source, release timing, and exact close/window rules."

    @staticmethod
    def _history_from_price(price: float, idx: int, live: bool) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        start = now_utc() - timedelta(hours=24)
        for step in range(8):
            wave = math.sin((idx + step) * 0.8) * 0.025
            drift = (step - 3.5) * (((idx % 7) - 3) / 650.0)
            historical_price = clamp(price + wave + drift, 0.03, 0.97)
            points.append(
                {
                    "time": iso_z(start + timedelta(hours=step * 3)),
                    "price": round(historical_price, 4),
                    "source": "snapshot-only" if live else "fixture-history",
                }
            )
        points[-1]["price"] = round(price, 4)
        return points


class OddsModelingAgent:
    def assess(self, candidate: MarketCandidate) -> AgentAssessment:
        prices = [float(point["price"]) for point in candidate.odds_history]
        slope = simple_slope(prices)
        velocity = prices[-1] - prices[-2] if len(prices) >= 2 else 0.0
        acceleration = 0.0
        if len(prices) >= 3:
            acceleration = (prices[-1] - prices[-2]) - (prices[-2] - prices[-3])
        volatility = pstdev(prices) if len(prices) > 1 else 0.0
        log_odds_now = logit(candidate.price)
        liquidity_depth = clamp(candidate.liquidity / 60000.0, 0.0, 1.0)
        spread_penalty = clamp(candidate.spread / 0.12, 0.0, 1.0)
        raw = (
            log_odds_now
            + (slope * 12.0)
            + (velocity * 4.5)
            + (acceleration * 2.0)
            + (candidate.stats.get("volume_shock", 0.0) * 0.22)
            + (liquidity_depth * 0.10)
            - (volatility * 1.2)
            - (spread_penalty * 0.16)
        )
        probability = clamp(logistic(raw), 0.03, 0.97)
        confidence = clamp(0.22 + liquidity_depth * 0.28 + abs(slope) * 12.0 - spread_penalty * 0.20, 0.05, 0.92)
        features = {
            "ols_trend_slope": round(slope, 5),
            "log_odds": round(log_odds_now, 4),
            "velocity": round(velocity, 5),
            "acceleration": round(acceleration, 5),
            "volatility": round(volatility, 5),
            "liquidity_depth": round(liquidity_depth, 4),
            "spread_penalty": round(spread_penalty, 4),
            "iv_note": "No IV applied unless an instrument has documented relevance and exclusion assumptions.",
        }
        flags = []
        if candidate.spread > 0.08:
            flags.append("wide_spread")
        if candidate.liquidity < 3000:
            flags.append("thin_liquidity")
        return AgentAssessment(
            agent="odds_modeling",
            probability=round(probability, 4),
            confidence=round(confidence, 4),
            score=round((probability - candidate.price) * confidence, 4),
            rationale="Odds history reviewed with log-odds, OLS slope, velocity, acceleration, volatility, spread, and liquidity.",
            features=features,
            flags=flags,
        )


class MarketContextNewsAgent:
    def assess(self, candidate: MarketCandidate) -> AgentAssessment:
        context_fields = candidate.context_fields()
        weighted_impact = 0.0
        credibility_total = 0.0
        timeline = []
        for item in candidate.news_items:
            credibility = float(item.get("credibility", 0.5))
            impact = float(item.get("impact", 0.0))
            weighted_impact += impact * credibility
            credibility_total += credibility
            timeline.append({"time": item.get("time", ""), "headline": item.get("headline", ""), "source": item.get("source", "")})
        source_confidence = clamp(credibility_total / max(len(candidate.news_items), 1), 0.0, 1.0)
        actor_strength = candidate.stats.get("actor_strength", 0.0)
        ambiguity = candidate.stats.get("ambiguity", 0.25)
        source_depth = candidate.stats.get("source_depth", 0.4)
        raw_context = candidate.price + weighted_impact * 0.34 + actor_strength * 0.08 - ambiguity * 0.07
        probability = clamp(raw_context, 0.03, 0.97)
        confidence = clamp(0.18 + source_confidence * 0.30 + source_depth * 0.22 - ambiguity * 0.22, 0.05, 0.90)
        flags = []
        if ambiguity > 0.35:
            flags.append("resolution_ambiguity")
        if source_confidence < 0.45:
            flags.append("weak_source_confidence")
        return AgentAssessment(
            agent="market_context_news",
            probability=round(probability, 4),
            confidence=round(confidence, 4),
            score=round((probability - candidate.price) * confidence, 4),
            rationale=f"{candidate.category} context reviewed across actors, timeline, source confidence, and settlement ambiguity.",
            features={
                "actors": candidate.actors,
                "actor_map": [{"actor": actor, "role": "primary_or_connected_actor"} for actor in candidate.actors],
                "timeline": timeline,
                "weighted_news_impact": round(weighted_impact, 4),
                "source_confidence": round(source_confidence, 4),
                "ambiguity": round(ambiguity, 4),
                "global_context_score": context_fields["global_context_score"],
                "category_context_score": context_fields["category_context_score"],
                "bet_research_score": context_fields["bet_research_score"],
                "source_coverage": context_fields["source_coverage"],
                "contradiction_flags": context_fields["contradiction_flags"],
                "staleness_flags": context_fields["staleness_flags"],
                "resolution_risk_flags": context_fields["resolution_risk_flags"],
            },
            flags=flags,
        )


class CategoryExpertAgent:
    def assess(self, candidate: MarketCandidate, odds: AgentAssessment, context: AgentAssessment) -> AgentAssessment:
        category_rules = {
            "macroeconomics": {"min_liquidity": 3000.0, "max_spread": 0.06, "ambiguity_cap": 0.34},
            "politics": {"min_liquidity": 3500.0, "max_spread": 0.065, "ambiguity_cap": 0.48},
            "stocks_trade": {"min_liquidity": 3500.0, "max_spread": 0.055, "ambiguity_cap": 0.34},
        }
        rule = category_rules.get(candidate.category, category_rules["macroeconomics"])
        ambiguity = candidate.stats.get("ambiguity", 0.3)
        agreement = 1.0 - min(abs(odds.probability - context.probability), 0.5) * 2.0
        probability = clamp((odds.probability * 0.46) + (context.probability * 0.38) + (candidate.price * 0.16), 0.03, 0.97)
        confidence = clamp((odds.confidence * 0.42) + (context.confidence * 0.38) + (agreement * 0.20), 0.05, 0.92)
        flags = []
        if candidate.liquidity < rule["min_liquidity"]:
            flags.append("category_liquidity_reject")
        if candidate.spread > rule["max_spread"]:
            flags.append("category_spread_reject")
        if ambiguity > rule["ambiguity_cap"]:
            flags.append("category_resolution_risk")
        vague_words = ("maybe", "rumor", "mention", "viral", "unclear")
        if any(word in candidate.market_title.lower() for word in vague_words):
            flags.append("vague_market_language")
        return AgentAssessment(
            agent=f"{candidate.category}_section_expert",
            probability=round(probability, 4),
            confidence=round(confidence, 4),
            score=round((probability - candidate.price) * confidence * agreement, 4),
            rationale=f"{category_label(candidate.category)} expert compared liquidity, spread, ambiguity, and model/context agreement.",
            features={
                "agreement": round(agreement, 4),
                "min_liquidity": rule["min_liquidity"],
                "max_spread": rule["max_spread"],
                "ambiguity_cap": rule["ambiguity_cap"],
                "category_notes": self._category_notes(candidate.category),
            },
            flags=flags,
        )

    @staticmethod
    def _category_notes(category: str) -> str:
        notes = {
            "macroeconomics": "Prioritize official release definitions, survey consensus, revision policy, and calendar timing.",
            "politics": "Prioritize official sources, actor incentives, deadline mechanics, and resolution ambiguity control.",
            "stocks_trade": "Prioritize official market closes, filings, trade releases, tariffs, liquidity, and exact time-window wording.",
        }
        return notes.get(category, notes["macroeconomics"])


class DecisionBankrollAgent:
    def __init__(self, bankroll: float = 100.0, deployment_budget: float = 100.0, target_bet_count: int | None = None) -> None:
        self.bankroll = bankroll
        self.deployment_budget = deployment_budget
        self.target_bet_count = target_bet_count

    def build_recommendations(
        self,
        candidates: list[MarketCandidate],
        assessments: dict[str, dict[str, AgentAssessment]],
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_context = candidate.context_fields()
            bundle = assessments[candidate.candidate_id]
            odds = bundle["odds"]
            context = bundle["context"]
            category = bundle["category"]
            blended = clamp((odds.probability * 0.50) + (context.probability * 0.28) + (category.probability * 0.22), 0.03, 0.97)
            confidence = clamp((odds.confidence * 0.42) + (context.confidence * 0.28) + (category.confidence * 0.30), 0.05, 0.95)
            edge = blended - candidate.price
            expected_value = (blended / max(candidate.price, 0.01)) - 1.0
            risk_tier = self._risk_tier(candidate, edge, confidence, category.flags)
            decision, reason = self._decision(candidate, edge, expected_value, confidence, risk_tier, category.flags)
            raw_stake = self._raw_stake(candidate, blended, risk_tier, decision)
            failure_conditions = self._failure_conditions(candidate, category.flags)
            research_penalty = (
                len(candidate_context["contradiction_flags"]) * 0.010
                + len(candidate_context["resolution_risk_flags"]) * 0.006
                + (0.004 if "fixture_context_not_live" in candidate_context["staleness_flags"] else 0.0)
            )
            recommendations.append(
                {
                    "candidate": candidate.to_dict(),
                    "assessments": {
                        "odds_modeling": odds.to_dict(),
                        "market_context_news": context.to_dict(),
                        "category_expert": category.to_dict(),
                    },
                    "blended_probability": round(blended, 4),
                    "confidence": round(confidence, 4),
                    "edge": round(edge, 4),
                    "expected_value": round(expected_value, 4),
                    "risk_tier": risk_tier,
                    "decision": decision,
                    "stake_units": 0.0,
                    "raw_stake_units": raw_stake,
                    "reason": reason,
                    "failure_conditions": failure_conditions,
                    "research_context": candidate_context,
                    "rank_score": round(
                        (expected_value * confidence)
                        + (candidate_context["bet_research_score"] * 0.015)
                        - candidate.spread
                        - research_penalty
                        - (0.03 if risk_tier == "VERY_RISKY" else 0.0),
                        5,
                    ),
                }
            )
        self._allocate_paper_budget(recommendations)
        return recommendations

    def reallocate_paper_budget(self, recommendations: list[dict[str, Any]]) -> None:
        for item in recommendations:
            if item["decision"] == "PAPER_BET":
                item["stake_units"] = 0.0
        self._allocate_paper_budget(recommendations)

    @staticmethod
    def _risk_tier(candidate: MarketCandidate, edge: float, confidence: float, flags: list[str]) -> str:
        if flags or candidate.spread > 0.08 or confidence < 0.24:
            return "VERY_RISKY"
        if edge > 0.075 and confidence > 0.62 and candidate.liquidity > 25000 and candidate.spread < 0.035:
            return "LOW"
        if edge > 0.04 and confidence > 0.45 and candidate.liquidity > 9000:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _decision(
        candidate: MarketCandidate,
        edge: float,
        expected_value: float,
        confidence: float,
        risk_tier: str,
        flags: list[str],
    ) -> tuple[str, str]:
        if flags:
            return "REJECTED", f"Rejected by category expert: {', '.join(flags)}"
        if edge < 0.018 or expected_value < 0.035:
            return "NO_BET", "No bet: forecast edge is too small after price and spread review"
        if confidence < 0.26:
            return "WATCHLIST", "Watchlist: edge exists but confidence is not high enough for main portfolio"
        if risk_tier == "VERY_RISKY":
            return "WATCHLIST", "Watchlist: very risky profile kept out of main portfolio"
        if candidate.source == "polymarket-gamma" and not candidate.resolution_notes:
            return "WATCHLIST", "Watchlist: live market needs manual resolution-rule review"
        return "PAPER_BET", "Paper bet accepted by EV, confidence, liquidity, and risk controls"

    def _raw_stake(self, candidate: MarketCandidate, blended_probability: float, risk_tier: str, decision: str) -> float:
        if decision != "PAPER_BET":
            return 0.0
        kelly = (blended_probability - candidate.price) / max(1.0 - candidate.price, 0.01)
        fractional = max(kelly, 0.0) * 0.30 * self.bankroll
        caps = {"LOW": 5.0, "MEDIUM": 3.0, "HIGH": 1.5, "VERY_RISKY": 0.5}
        floor = {"LOW": 2.0, "MEDIUM": 1.0, "HIGH": 0.5, "VERY_RISKY": 0.25}
        return round(clamp(fractional, floor[risk_tier], caps[risk_tier]), 2)

    @staticmethod
    def _failure_conditions(candidate: MarketCandidate, flags: list[str]) -> list[str]:
        context_fields = candidate.context_fields()
        conditions = [
            "forecast edge closes below 2 percentage points",
            "spread widens materially before entry",
            "resolution wording changes or becomes ambiguous",
        ]
        if candidate.category == "politics":
            conditions.append("new official/context source contradicts the thesis")
        if flags:
            conditions.extend(flags)
        conditions.extend(context_fields["contradiction_flags"])
        conditions.extend(context_fields["resolution_risk_flags"])
        return conditions

    def _allocate_paper_budget(self, recommendations: list[dict[str, Any]]) -> None:
        budget = min(self.deployment_budget, self.bankroll)
        event_exposure: dict[str, float] = {}
        category_exposure: dict[str, float] = {}
        remaining = budget
        target_bet_count = max(int(self.target_bet_count or 0), 0)
        minimum_stake = 0.25
        eligible = [
            item
            for item in sorted(recommendations, key=lambda row: row["rank_score"], reverse=True)
            if item["decision"] == "PAPER_BET"
        ]
        max_seeded_by_budget = int(budget // minimum_stake)
        selected_limit = min(len(eligible), max_seeded_by_budget)
        if target_bet_count:
            selected_limit = min(selected_limit, target_bet_count)
        selected = eligible[:selected_limit]

        for item in selected:
            candidate = item["candidate"]
            event_id = str(candidate["event_id"])
            category = str(candidate["category"])
            raw = float(item["raw_stake_units"])
            event_room = max(10.0 - event_exposure.get(event_id, 0.0), 0.0)
            stake = round(min(raw, minimum_stake, event_room, remaining), 2)
            if stake <= 0:
                item["decision"] = "WATCHLIST"
                item["reason"] = "Watchlist: portfolio cap reached before allocation"
                continue
            item["stake_units"] = stake
            event_exposure[event_id] = event_exposure.get(event_id, 0.0) + stake
            category_exposure[category] = category_exposure.get(category, 0.0) + stake
            remaining = round(remaining - stake, 2)
            if remaining <= 0:
                break

        # Paper mode first stakes every selected approved bet, then allocates the rest by
        # category diversity and reliability while preserving event and risk-tier caps.
        top_up_eligible = [item for item in selected if item["decision"] == "PAPER_BET" and float(item["stake_units"]) > 0.0]
        total_base_cap = sum(self._risk_tier_cap(item) for item in top_up_eligible) or 1.0
        cap_multiplier = max(1.0, budget / total_base_cap)
        category_targets = self._category_budget_targets(top_up_eligible, budget)
        while remaining >= 0.01:
            progressed = False
            prioritized = sorted(
                top_up_eligible,
                key=lambda item: (
                    self._category_underfill(item, category_exposure, category_targets),
                    self._reliability_weight(item),
                    float(item["rank_score"]),
                ),
                reverse=True,
            )
            for item in prioritized:
                category = str(item["candidate"]["category"])
                category_room = max(category_targets.get(category, 0.0) - category_exposure.get(category, 0.0), 0.0)
                if category_room <= 0.0:
                    continue
                add = self._stake_addition(item, event_exposure, remaining, category_room=category_room, cap_multiplier=cap_multiplier)
                if add <= 0:
                    continue
                remaining = self._apply_stake_addition(item, add, event_exposure, category_exposure, remaining)
                progressed = True
                if remaining < 0.01:
                    break
            if not progressed:
                break

        while remaining >= 0.01:
            # Final residual pass: keep the paper book fully staked whenever any approved
            # bet still has room, but favor under-exposed categories before pure rank.
            prioritized = sorted(
                top_up_eligible,
                key=lambda item: (
                    -category_exposure.get(str(item["candidate"]["category"]), 0.0),
                    self._reliability_weight(item),
                    float(item["rank_score"]),
                ),
                reverse=True,
            )
            progressed = False
            for item in prioritized:
                add = self._stake_addition(item, event_exposure, remaining, cap_multiplier=cap_multiplier)
                if add <= 0:
                    continue
                remaining = self._apply_stake_addition(item, add, event_exposure, category_exposure, remaining)
                progressed = True
                if remaining < 0.01:
                    break
            if not progressed:
                break

        while remaining >= 0.01 and top_up_eligible:
            # Paper-only residual: if strict caps strand a small balance, keep the
            # bankroll fully deployed by adding to the least-exposed reliable buckets.
            prioritized = sorted(
                top_up_eligible,
                key=lambda item: (
                    -category_exposure.get(str(item["candidate"]["category"]), 0.0),
                    self._reliability_weight(item),
                    float(item["rank_score"]),
                ),
                reverse=True,
            )
            for item in prioritized:
                add = round(min(0.25, remaining), 2)
                if add <= 0:
                    continue
                remaining = self._apply_stake_addition(item, add, event_exposure, category_exposure, remaining)
                if remaining < 0.01:
                    break

        for item in eligible:
            if item["decision"] == "PAPER_BET" and float(item["stake_units"]) <= 0.0:
                item["decision"] = "WATCHLIST"
                item["reason"] = "Watchlist: qualified but the 100-coin paper deployment budget was already allocated"

    @staticmethod
    def _risk_tier_cap(item: dict[str, Any]) -> float:
        return {"LOW": 5.0, "MEDIUM": 3.0, "HIGH": 1.5, "VERY_RISKY": 0.5}.get(str(item["risk_tier"]), 1.0)

    @staticmethod
    def _reliability_weight(item: dict[str, Any]) -> float:
        tier_weight = {"LOW": 1.25, "MEDIUM": 1.0, "HIGH": 0.72, "VERY_RISKY": 0.35}.get(str(item["risk_tier"]), 0.6)
        confidence = clamp(float(item.get("confidence", 0.0)), 0.05, 0.95)
        ev = clamp(float(item.get("expected_value", 0.0)), 0.0, 1.0)
        return round(tier_weight * (0.60 + confidence) * (1.0 + ev * 0.25), 6)

    def _category_budget_targets(self, items: list[dict[str, Any]], budget: float) -> dict[str, float]:
        categories = sorted({str(item["candidate"]["category"]) for item in items})
        if not categories:
            return {}
        equal_share = 1.0 / len(categories)
        category_weights = {
            category: sum(self._reliability_weight(item) for item in items if str(item["candidate"]["category"]) == category)
            for category in categories
        }
        total_weight = sum(category_weights.values()) or 1.0
        return {
            category: round(budget * ((equal_share * 0.55) + ((category_weights[category] / total_weight) * 0.45)), 2)
            for category in categories
        }

    @staticmethod
    def _category_underfill(
        item: dict[str, Any],
        category_exposure: dict[str, float],
        category_targets: dict[str, float],
    ) -> float:
        category = str(item["candidate"]["category"])
        target = max(category_targets.get(category, 0.0), 0.01)
        return max((target - category_exposure.get(category, 0.0)) / target, 0.0)

    def _stake_addition(
        self,
        item: dict[str, Any],
        event_exposure: dict[str, float],
        remaining: float,
        *,
        category_room: float | None = None,
        cap_multiplier: float = 1.0,
    ) -> float:
        event_id = str(item["candidate"]["event_id"])
        event_room = max(10.0 - event_exposure.get(event_id, 0.0), 0.0)
        stake_room = max((self._risk_tier_cap(item) * cap_multiplier) - float(item["stake_units"]), 0.0)
        rooms = [0.25, event_room, stake_room, remaining]
        if category_room is not None:
            rooms.append(category_room)
        return round(min(rooms), 2)

    @staticmethod
    def _apply_stake_addition(
        item: dict[str, Any],
        add: float,
        event_exposure: dict[str, float],
        category_exposure: dict[str, float],
        remaining: float,
    ) -> float:
        candidate = item["candidate"]
        event_id = str(candidate["event_id"])
        category = str(candidate["category"])
        item["stake_units"] = round(float(item["stake_units"]) + add, 2)
        event_exposure[event_id] = round(event_exposure.get(event_id, 0.0) + add, 2)
        category_exposure[category] = round(category_exposure.get(category, 0.0) + add, 2)
        return round(remaining - add, 2)


class EvaluationLearningAgent:
    def evaluate(self, recommendations: list[dict[str, Any]], starting_bankroll: float = 100.0) -> dict[str, Any]:
        bankroll = starting_bankroll
        peak = bankroll
        curve: list[dict[str, Any]] = [{"label": "start", "bankroll": bankroll}]
        bets = [item for item in recommendations if item["decision"] == "PAPER_BET" and float(item["stake_units"]) > 0]
        wins = 0
        losses = 0
        pnl_total = 0.0
        mistakes: list[dict[str, Any]] = []

        for item in bets:
            candidate = item["candidate"]
            actual = candidate.get("resolved_outcome")
            if actual is None:
                item["outcome"] = "PENDING"
                item["pnl_units"] = 0.0
                continue
            won = int(actual) == 1
            stake = float(item["stake_units"])
            price = float(candidate["price"])
            pnl = round(stake * ((1.0 - price) / price), 4) if won else round(-stake, 4)
            bankroll = round(bankroll + pnl, 4)
            peak = max(peak, bankroll)
            pnl_total = round(pnl_total + pnl, 4)
            wins += 1 if won else 0
            losses += 0 if won else 1
            item["outcome"] = "WIN" if won else "LOSS"
            item["pnl_units"] = pnl
            item["bankroll_after"] = bankroll
            curve.append({"label": candidate["candidate_id"], "bankroll": bankroll})
            if not won:
                mistakes.append(self._mistake_review(item))

        staked = round(sum(float(item["stake_units"]) for item in bets), 4)
        avg_odds = round(mean([float(item["candidate"]["decimal_odds"]) for item in bets]), 4) if bets else 0.0
        brier = self._brier(recommendations)
        log_loss = self._log_loss(recommendations)
        classification = self._classification_metrics(recommendations)
        max_drawdown = round(max((peak - point["bankroll"]) / peak for point in curve), 4) if peak else 0.0
        return {
            "metrics": {
                "research_only": True,
                "mode": PAPER_MODE,
                "paper_trading_only": True,
                "active_sections": list(ACTIVE_CATEGORIES),
                "agent_contract_version": "three_agent_v1",
                "reliability_labels": AGENT_CONTRACT["reliability_labels"],
                "starting_bankroll_units": starting_bankroll,
                "deployment_budget_units": starting_bankroll,
                "ending_bankroll_units": bankroll,
                "unallocated_budget_units": round(max(starting_bankroll - staked, 0.0), 4),
                "candidate_count": len(recommendations),
                "paper_bet_count": len(bets),
                "watchlist_count": sum(1 for item in recommendations if item["decision"] == "WATCHLIST"),
                "rejected_count": sum(1 for item in recommendations if item["decision"] == "REJECTED"),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / max(wins + losses, 1), 4),
                "total_staked_units": staked,
                "total_pnl_units": pnl_total,
                "simulated_roi": round(pnl_total / staked, 4) if staked else 0.0,
                "average_decimal_odds": avg_odds,
                "average_expected_value": round(mean([item["expected_value"] for item in bets]), 4) if bets else 0.0,
                "max_drawdown": max_drawdown,
                "brier_score": brier,
                "log_loss": log_loss,
                "classification": classification,
                "calibration": self._calibration(recommendations),
            },
            "bankroll_curve": curve,
            "mistakes": mistakes,
            "agent_performance": self._agent_performance(recommendations),
        }

    @staticmethod
    def _brier(recommendations: list[dict[str, Any]]) -> float:
        settled = [item for item in recommendations if item["candidate"].get("resolved_outcome") is not None]
        if not settled:
            return 0.0
        return round(
            mean((float(item["blended_probability"]) - float(item["candidate"]["resolved_outcome"])) ** 2 for item in settled),
            4,
        )

    @staticmethod
    def _log_loss(recommendations: list[dict[str, Any]]) -> float:
        settled = [item for item in recommendations if item["candidate"].get("resolved_outcome") is not None]
        if not settled:
            return 0.0
        total = 0.0
        for item in settled:
            p = clamp(float(item["blended_probability"]), 0.001, 0.999)
            actual = float(item["candidate"]["resolved_outcome"])
            total += -((actual * math.log(p)) + ((1.0 - actual) * math.log(1.0 - p)))
        return round(total / len(settled), 4)

    @staticmethod
    def _classification_metrics(recommendations: list[dict[str, Any]], threshold: float = 0.5) -> dict[str, Any]:
        settled = [item for item in recommendations if item["candidate"].get("resolved_outcome") is not None]
        if not settled:
            return {
                "threshold": threshold,
                "sample_count": 0,
                "true_positive": 0,
                "false_positive": 0,
                "true_negative": 0,
                "false_negative": 0,
                "precision": None,
                "recall": None,
                "specificity": None,
                "accuracy": None,
            }
        true_positive = false_positive = true_negative = false_negative = 0
        for item in settled:
            predicted_yes = float(item["blended_probability"]) >= threshold
            actual_yes = int(item["candidate"]["resolved_outcome"]) == 1
            if predicted_yes and actual_yes:
                true_positive += 1
            elif predicted_yes and not actual_yes:
                false_positive += 1
            elif not predicted_yes and actual_yes:
                false_negative += 1
            else:
                true_negative += 1
        return {
            "threshold": threshold,
            "sample_count": len(settled),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
            "precision": _safe_ratio(true_positive, true_positive + false_positive),
            "recall": _safe_ratio(true_positive, true_positive + false_negative),
            "specificity": _safe_ratio(true_negative, true_negative + false_positive),
            "accuracy": _safe_ratio(true_positive + true_negative, len(settled)),
        }

    @staticmethod
    def _calibration(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets = [
            ("0.00-0.35", 0.0, 0.35),
            ("0.35-0.50", 0.35, 0.50),
            ("0.50-0.65", 0.50, 0.65),
            ("0.65-0.80", 0.65, 0.80),
            ("0.80-1.00", 0.80, 1.01),
        ]
        rows = []
        for label, low, high in buckets:
            group = [
                item
                for item in recommendations
                if low <= float(item["blended_probability"]) < high and item["candidate"].get("resolved_outcome") is not None
            ]
            actual = mean([float(item["candidate"]["resolved_outcome"]) for item in group]) if group else None
            rows.append(
                {
                    "label": label,
                    "count": len(group),
                    "predicted_midpoint": round((low + min(high, 1.0)) / 2.0, 3),
                    "actual_win_rate": round(actual, 4) if actual is not None else None,
                }
            )
        return rows

    @staticmethod
    def _agent_performance(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        agent_keys = ("odds_modeling", "market_context_news", "category_expert")
        rows = []
        for key in agent_keys:
            settled = [item for item in recommendations if item["candidate"].get("resolved_outcome") is not None]
            if not settled:
                rows.append({"agent": key, "score": 0.0, "brier": 0.0, "confidence": 0.0, "notes": "No settled outcomes yet"})
                continue
            brier = mean(
                (float(item["assessments"][key]["probability"]) - float(item["candidate"]["resolved_outcome"])) ** 2
                for item in settled
            )
            confidence = mean(float(item["assessments"][key]["confidence"]) for item in settled)
            rows.append(
                {
                    "agent": key,
                    "score": round(max(0.0, 1.0 - brier) * 100.0, 2),
                    "brier": round(brier, 4),
                    "confidence": round(confidence, 4),
                    "notes": "Higher score means lower Brier error on fixture-settled candidates.",
                }
            )
        bet_settled = [item for item in recommendations if item.get("outcome") in {"WIN", "LOSS"}]
        decision_score = mean([1.0 if item["outcome"] == "WIN" else 0.0 for item in bet_settled]) if bet_settled else 0.0
        rows.append(
            {
                "agent": "decision_bankroll",
                "score": round(decision_score * 100.0, 2),
                "brier": None,
                "confidence": None,
                "notes": "Decision layer score is the paper-bet win rate before long-run calibration is available.",
            }
        )
        return rows

    @staticmethod
    def _mistake_review(item: dict[str, Any]) -> dict[str, Any]:
        assessments = item["assessments"]
        high_agents = [
            key
            for key, assessment in assessments.items()
            if float(assessment["probability"]) > 0.58 and float(assessment["confidence"]) > 0.35
        ]
        category = item["candidate"]["category"]
        if "market_context_news" in high_agents:
            mistake_type = "bad_news_or_context_read"
        elif "odds_modeling" in high_agents:
            mistake_type = "odds_trend_overfit"
        elif item["candidate"]["spread"] > 0.05:
            mistake_type = "poor_liquidity_or_spread"
        elif category == "politics":
            mistake_type = "ambiguity_or_actor_timing"
        else:
            mistake_type = "variance_or_stake_timing"
        return {
            "candidate_id": item["candidate"]["candidate_id"],
            "market_title": item["candidate"]["market_title"],
            "category": category,
            "stake_units": item["stake_units"],
            "pnl_units": item.get("pnl_units", 0.0),
            "mistake_type": mistake_type,
            "agent_flags": high_agents,
            "learning_note": "Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance.",
        }


class MultiAgentPipeline:
    def __init__(
        self,
        market_data: MarketDataAgent | None = None,
        odds_agent: OddsModelingAgent | None = None,
        context_agent: MarketContextNewsAgent | None = None,
        category_agent: CategoryExpertAgent | None = None,
        decision_agent: DecisionBankrollAgent | None = None,
        evaluation_agent: EvaluationLearningAgent | None = None,
    ) -> None:
        self.market_data = market_data or MarketDataAgent()
        self.odds_agent = odds_agent or OddsModelingAgent()
        self.context_agent = context_agent or MarketContextNewsAgent()
        self.category_agent = category_agent or CategoryExpertAgent()
        self.decision_agent = decision_agent or DecisionBankrollAgent()
        self.evaluation_agent = evaluation_agent or EvaluationLearningAgent()

    def run(self, source_mode: str = "fixture", target_count: int = 300) -> MultiAgentRun:
        candidates = self.market_data.load_candidates(source_mode=source_mode, target_count=target_count)
        assessments: dict[str, dict[str, AgentAssessment]] = {}
        for candidate in candidates:
            odds = self.odds_agent.assess(candidate)
            context = self.context_agent.assess(candidate)
            category = self.category_agent.assess(candidate, odds, context)
            assessments[candidate.candidate_id] = {"odds": odds, "context": context, "category": category}
        recommendations = self.decision_agent.build_recommendations(candidates, assessments)
        recommendations.sort(key=lambda item: item["rank_score"], reverse=True)
        evaluation = self.evaluation_agent.evaluate(recommendations)
        ranked_paper_bets = [item for item in recommendations if item["decision"] == "PAPER_BET"]
        recommendations_by_date = sorted(recommendations, key=_recommendation_published_sort_key, reverse=True)
        paper_bets = [item for item in recommendations_by_date if item["decision"] == "PAPER_BET"]
        watchlist = [item for item in recommendations_by_date if item["decision"] == "WATCHLIST"]
        rejected = [item for item in recommendations_by_date if item["decision"] == "REJECTED"]
        category_stats = self._category_stats(recommendations)
        return MultiAgentRun(
            run_id=f"multi-agent-{iso_z(now_utc())}",
            created_at=iso_z(now_utc()),
            mode=PAPER_MODE,
            source_mode=source_mode,
            source_note=self.market_data.source_note,
            candidates=[candidate.to_dict() for candidate in candidates],
            recommendations=recommendations_by_date,
            paper_bets=paper_bets,
            watchlist=watchlist,
            rejected=rejected,
            top_bets=ranked_paper_bets[:10],
            category_stats=category_stats,
            agent_performance=evaluation["agent_performance"],
            metrics=evaluation["metrics"],
            bankroll_curve=evaluation["bankroll_curve"],
            mistakes=evaluation["mistakes"],
        )

    @staticmethod
    def _category_stats(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for category in ACTIVE_CATEGORIES:
            group = [item for item in recommendations if item["candidate"]["category"] == category]
            if not group:
                continue
            bets = [item for item in group if item["decision"] == "PAPER_BET" and float(item["stake_units"]) > 0.0]
            settled = [item for item in bets if item.get("outcome") in {"WIN", "LOSS"}]
            wins = sum(1 for item in settled if item["outcome"] == "WIN")
            staked = sum(float(item["stake_units"]) for item in bets)
            pnl = sum(float(item.get("pnl_units", 0.0)) for item in bets)
            rows.append(
                {
                    "category": category,
                    "candidate_count": len(group),
                    "paper_bet_count": len(bets),
                    "watchlist_count": sum(1 for item in group if item["decision"] == "WATCHLIST"),
                    "rejected_count": sum(1 for item in group if item["decision"] == "REJECTED"),
                    "win_rate": round(wins / max(len(settled), 1), 4),
                    "total_staked_units": round(staked, 4),
                    "pnl_units": round(pnl, 4),
                    "average_ev": round(mean([item["expected_value"] for item in group]), 4),
                    "average_spread": round(mean([item["candidate"]["spread"] for item in group]), 4),
                    "average_decimal_odds": round(mean([item["candidate"]["decimal_odds"] for item in group]), 4),
                    "top_pick_ids": [item["candidate"]["candidate_id"] for item in bets[:3]],
                }
            )
        return rows


def _recommendation_published_sort_key(item: dict[str, Any]) -> str:
    candidate = item.get("candidate", {})
    return str(candidate.get("published_at") or candidate.get("updated_at") or candidate.get("end_time") or "")


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)
