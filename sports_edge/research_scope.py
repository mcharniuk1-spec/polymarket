from __future__ import annotations

from typing import Any


ACTIVE_CATEGORIES = ("macroeconomics", "politics", "stocks_trade")

CATEGORY_LABELS = {
    "macroeconomics": "Macroeconomics",
    "politics": "Politics",
    "stocks_trade": "Stocks / Trade",
}

CATEGORY_ALIASES = {
    "macroeconomics": ("macroeconomics", "macro", "economics", "economy"),
    "politics": ("politics", "politic", "geopolitics", "geopolitic", "policy"),
    "stocks_trade": ("stocks_trade", "stocks", "stock", "equities", "equity", "trade", "tariff", "company", "macro", "global"),
}

LEGACY_CATEGORY_MAP = {
    "macro": "macroeconomics",
    "economics": "macroeconomics",
    "economy": "macroeconomics",
    "geopolitics": "politics",
    "geopolitic": "politics",
    "politic": "politics",
    "politics": "politics",
    "stock": "stocks_trade",
    "stocks": "stocks_trade",
    "equity": "stocks_trade",
    "equities": "stocks_trade",
    "trade": "stocks_trade",
    "tariff": "stocks_trade",
}

OUT_OF_SCOPE_CATEGORIES = {"sports", "crypto", "weather", "culture"}

RELIABILITY_LABELS = {
    "reliable": {
        "min_confidence": 0.80,
        "description": "confidence > 0.80 with strong evidence quality and model agreement",
    },
    "possible/probable": {
        "min_confidence": 0.50,
        "description": "confidence 0.50-0.80 or mixed evidence",
    },
    "unreliable/reject": {
        "min_confidence": 0.0,
        "description": "confidence < 0.50, weak data, unclear rules, low liquidity, high spread, or model disagreement",
    },
}

AGENT_CONTRACT = {
    "mode": "paper_trading_only",
    "sections": [
        {"id": category, "label": CATEGORY_LABELS[category]}
        for category in ACTIVE_CATEGORIES
    ],
    "agents": [
        {
            "id": "context_agent",
            "label": "Context Agent",
            "responsibility": (
                "Run broad daily context for macroeconomics, politics, and stocks/trade, then candidate-specific "
                "context for relevant markets with sources, relevance, uncertainty, and confidence."
            ),
            "internal_models": ["news_catalyst_sentiment", "source_reliability", "resolution_wording_risk"],
        },
        {
            "id": "data_agent",
            "label": "Data Agent",
            "responsibility": (
                "Gather read-only Polymarket data, spreads, liquidity, volume, history, rules, resolution criteria, "
                "time to resolution, and external numeric data readiness."
            ),
            "internal_models": ["market_implied_probability", "liquidity_spread", "base_rate_history", "statistical_ml"],
        },
        {
            "id": "decision_agent",
            "label": "Decision Agent",
            "responsibility": (
                "Combine context and data into reject/watchlist/paper-bet decisions, size paper risk, record reasoning, "
                "and update the learning base after outcomes."
            ),
            "internal_models": ["bayesian_update", "portfolio_ev_risk", "model_disagreement"],
        },
    ],
    "safety": {
        "real_money_betting": False,
        "wallet_signing": False,
        "order_execution": False,
        "credential_storage": False,
    },
    "reliability_labels": RELIABILITY_LABELS,
}


def normalize_category_id(category: str | None) -> str | None:
    raw = str(category or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in ACTIVE_CATEGORIES:
        return raw
    if raw in OUT_OF_SCOPE_CATEGORIES:
        return None
    return LEGACY_CATEGORY_MAP.get(raw)


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def source_categories_for(category: str, *, include_global: bool = False, include_polymarket: bool = False) -> set[str]:
    normalized = normalize_category_id(category) or category
    categories = set(CATEGORY_ALIASES.get(normalized, (normalized,)))
    if include_global:
        categories.add("global")
    if include_polymarket:
        categories.add("polymarket")
    return categories


def is_active_category(category: str | None) -> bool:
    return normalize_category_id(category) in ACTIVE_CATEGORIES


def active_scope_filter(source: Any) -> bool:
    category = str(getattr(source, "category", "") or "")
    if category in {"global", "polymarket"}:
        return True
    return any(category in source_categories_for(active) for active in ACTIVE_CATEGORIES)
