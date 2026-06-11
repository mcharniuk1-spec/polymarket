from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .research_scope import ACTIVE_CATEGORIES
from .schemas import ExternalObservation, SourceRecord, stable_id


@dataclass(frozen=True)
class ExternalAdapterBundle:
    source_records: list[SourceRecord]
    observations: list[ExternalObservation]
    warnings: list[str]


FetchResult = dict[str, Any]


def collect_external_adapter_bundle(
    *,
    run_id: str,
    observed_at: str,
    source_mode: str,
    fetcher: Any | None = None,
) -> ExternalAdapterBundle:
    """Return normalized external observations for the active sections.

    Fixture mode uses deterministic as-of-safe records that emulate official release calendars,
    election/institutional calendars, and stock/trade market data. Live mode uses public read-only
    adapters and only emits decision evidence when a source-specific parser extracts a structured
    numeric observation. Reachability checks remain explicitly marked as source-health metadata.
    """

    source_records = external_source_records()
    warnings: list[str] = []
    if source_mode == "fixture":
        observations = fixture_external_observations(run_id=run_id, observed_at=observed_at)
        warnings.append("External adapters used deterministic fixture observations; no live official-source fetch occurred.")
    else:
        observations, warnings = live_external_observations(
            run_id=run_id,
            observed_at=observed_at,
            fetcher=fetcher,
        )
    return ExternalAdapterBundle(source_records=source_records, observations=observations, warnings=warnings)


def external_source_records() -> list[SourceRecord]:
    return [
        SourceRecord(
            source_id="official_macro_calendar",
            name="Official macroeconomic release calendar",
            source_type="official",
            category="macroeconomics",
            reliability_tier="primary",
            access_policy="fixture_public_read_only_adapter",
            freshness_sla_minutes=1440,
            url="https://www.bls.gov/schedule/news_release/",
            notes="Fixture/live adapter models BLS/BEA/Federal Reserve release-calendar timing. Live rows must come from parser-verified public data.",
        ),
        SourceRecord(
            source_id="macro_consensus_fixture",
            name="Macro consensus fixture",
            source_type="expert_commentary",
            category="macroeconomics",
            reliability_tier="medium",
            access_policy="fixture_no_live_license_claim",
            freshness_sla_minutes=1440,
            notes="Consensus-style fixture value for testing Bayesian consensus plumbing only.",
        ),
        SourceRecord(
            source_id="official_politics_calendar",
            name="Official political/election calendar",
            source_type="official",
            category="politics",
            reliability_tier="primary",
            access_policy="fixture_public_read_only_adapter",
            freshness_sla_minutes=1440,
            url="https://www.usa.gov/election-office",
            notes="Fixture/live adapter models official election/institutional deadline timing. Risk proxies require structured approved inputs.",
        ),
        SourceRecord(
            source_id="official_stocks_trade_calendar",
            name="Official stocks/trade event calendar",
            source_type="official",
            category="stocks_trade",
            reliability_tier="primary",
            access_policy="fixture_public_read_only_adapter",
            freshness_sla_minutes=1440,
            url="https://www.sec.gov/edgar/search-and-access",
            notes="Fixture/live adapter models SEC/company-calendar, close-price, volatility, and trade-policy event features from structured public inputs.",
        ),
        SourceRecord(
            source_id="market_data_fixture",
            name="Stocks and index market-data fixture",
            source_type="market_data",
            category="stocks_trade",
            reliability_tier="medium",
            access_policy="fixture_no_live_license_claim",
            freshness_sla_minutes=60,
            notes="Fixture market-data rows for volatility and recent-return features; not a licensed live quote feed.",
        ),
        SourceRecord(
            source_id="configured_market_data_provider",
            name="Configured stocks/index market-data provider",
            source_type="market_data",
            category="stocks_trade",
            reliability_tier="medium",
            access_policy="approved_public_or_configured_provider_only",
            freshness_sla_minutes=60,
            notes="Structured live market-data rows may be used only from an approved public or configured provider; no brokerage or trading endpoints.",
        ),
    ]


def fixture_external_observations(*, run_id: str, observed_at: str) -> list[ExternalObservation]:
    rows = [
        _observation(
            run_id,
            observed_at,
            "official_macro_calendar",
            "macroeconomics",
            "days_until_next_release",
            4.0,
            "days",
            {
                "event": "CPI release",
                "officialSourceClass": "BLS release calendar",
                "marketType": "macro_release_threshold",
                "relevance": "near-term catalyst timing",
            },
        ),
        _observation(
            run_id,
            observed_at,
            "macro_consensus_fixture",
            "macroeconomics",
            "consensus_surprise_z",
            0.18,
            "z_score",
            {
                "event": "CPI consensus proxy",
                "direction": "slightly_above_consensus",
                "marketType": "macro_release_threshold",
                "relevance": "Bayesian consensus input",
            },
        ),
        _observation(
            run_id,
            observed_at,
            "official_politics_calendar",
            "politics",
            "deadline_delay_risk_index",
            0.32,
            "probability_proxy",
            {
                "event": "Election certification deadline",
                "officialSourceClass": "election board/institutional calendar",
                "marketType": "political_deadline_delay",
                "relevance": "institutional timing and rule-risk input",
            },
        ),
        _observation(
            run_id,
            observed_at,
            "official_stocks_trade_calendar",
            "stocks_trade",
            "event_window_days",
            2.0,
            "days",
            {
                "event": "Weekly close / company catalyst window",
                "officialSourceClass": "exchange close / SEC company calendar",
                "marketType": "equity_close_threshold",
                "relevance": "event-window timing",
            },
        ),
        _observation(
            run_id,
            observed_at,
            "market_data_fixture",
            "stocks_trade",
            "underlying_return_1d",
            0.012,
            "return",
            {
                "instrument": "NVDA fixture proxy",
                "volatility_5d": 0.034,
                "marketType": "equity_close_threshold",
                "relevance": "recent momentum and volatility input",
            },
        ),
    ]
    return rows


def live_external_observations(
    *,
    run_id: str,
    observed_at: str,
    fetcher: Any | None = None,
) -> tuple[list[ExternalObservation], list[str]]:
    """Fetch public official sources without credentials and return parsed or health observations.

    Unparsed pages are never promoted into decision evidence. If a parser cannot extract a known
    numeric contract, the row is recorded as source-health metadata only.
    """

    fetch = fetcher or _safe_public_fetch
    probes = [
        (
            "official_macro_calendar",
            "macroeconomics",
            "https://www.bls.gov/schedule/news_release/",
            _parse_macro_release_observations,
        ),
        (
            "official_politics_calendar",
            "politics",
            "https://www.usa.gov/election-office",
            _parse_politics_calendar_observations,
        ),
        (
            "official_stocks_trade_calendar",
            "stocks_trade",
            "https://www.sec.gov/edgar/search-and-access",
            _parse_stocks_trade_observations,
        ),
    ]
    observations: list[ExternalObservation] = []
    warnings: list[str] = []
    parsed_count = 0
    for source_id, category, url, parser in probes:
        try:
            result = fetch(url)
            ok = bool(result.get("ok"))
            if not ok:
                warnings.append(f"{source_id} public probe failed with status {result.get('status')}.")
                observations.append(_health_observation(run_id, observed_at, source_id, category, url, result))
                continue
            parsed = parser(run_id=run_id, observed_at=observed_at, result=result)
            if parsed:
                observations.extend(parsed)
                parsed_count += len(parsed)
            else:
                observations.append(_health_observation(run_id, observed_at, source_id, category, url, result))
                warnings.append(f"{source_id} reachable but no parser-verified numeric observation was extracted.")
        except Exception as exc:
            warnings.append(f"{source_id} public probe failed: {type(exc).__name__}.")
            observations.append(_pending_observation(run_id=run_id, observed_at=observed_at, category=category))
    if not warnings:
        warnings.append(f"Live external adapters parsed {parsed_count} read-only public observations; no restricted data was used.")
    return observations, warnings


def _health_observation(
    run_id: str,
    observed_at: str,
    source_id: str,
    category: str,
    url: str,
    result: FetchResult,
) -> ExternalObservation:
    ok = bool(result.get("ok"))
    return _observation(
        run_id,
        observed_at,
        source_id,
        category,
        "official_source_http_ok",
        1.0 if ok else 0.0,
        "boolean",
        {
            "status": "reachable" if ok else "unreachable",
            "url": url,
            "httpStatus": result.get("status"),
            "contentType": result.get("content_type"),
            "relevance": "source_health_not_decision_evidence",
            "note": "Read-only source availability probe; no live numeric evidence was parsed.",
        },
    )


def _pending_observation(*, run_id: str, observed_at: str, category: str) -> ExternalObservation:
    source_ids = {
        "macroeconomics": "official_macro_calendar",
        "politics": "official_politics_calendar",
        "stocks_trade": "official_stocks_trade_calendar",
    }
    return ExternalObservation(
        observation_id=stable_id(run_id, category, "external-live-pending", observed_at),
        source_id=source_ids[category],
        category=category,
        observed_at=observed_at,
        as_of=observed_at,
        metric_name="adapter_readiness",
        metric_value=0.0,
        unit="pending_live_adapter",
        payload={
            "status": "live_official_adapter_pending",
            "note": "No live external evidence was used. This row must not strengthen a decision.",
        },
    )


def _safe_public_fetch(url: str) -> FetchResult:
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "text/html,application/json;q=0.8,*/*;q=0.5",
            "User-Agent": "polymarket-research-readonly/0.1",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read(200000)
            content_type = response.headers.get("content-type")
            return {
                "ok": 200 <= int(response.status) < 400,
                "status": int(response.status),
                "content_type": content_type,
                "text": _decode_body(body),
            }
    except HTTPError as exc:
        return {"ok": False, "status": int(exc.code), "content_type": None}
    except (URLError, TimeoutError):
        return {"ok": False, "status": None, "content_type": None}


def _parse_macro_release_observations(*, run_id: str, observed_at: str, result: FetchResult) -> list[ExternalObservation]:
    event = _first_event(result, preferred_terms=("cpi", "consumer price", "inflation"))
    event_date = _event_date(event) if event else _first_iso_date(_result_text(result))
    if not event_date:
        return []
    days = _days_until(event_date, observed_at)
    if days is None:
        return []
    return [
        _observation(
            run_id,
            observed_at,
            "official_macro_calendar",
            "macroeconomics",
            "days_until_next_release",
            float(days),
            "days",
            {
                "event": str(event.get("name") or event.get("title") or "Official macro release") if event else "Official macro release",
                "eventDate": event_date,
                "officialSourceClass": "official release calendar",
                "marketType": "macro_release_threshold",
                "relevance": "parser_verified_official_calendar_timing",
            },
        )
    ]


def _parse_politics_calendar_observations(*, run_id: str, observed_at: str, result: FetchResult) -> list[ExternalObservation]:
    event = _first_event(result, preferred_terms=("certification", "election", "deadline", "vote"))
    if not event:
        return []
    rows: list[ExternalObservation] = []
    event_date = _event_date(event)
    if event_date:
        days = _days_until(event_date, observed_at)
        if days is not None:
            rows.append(
                _observation(
                    run_id,
                    observed_at,
                    "official_politics_calendar",
                    "politics",
                    "days_until_political_deadline",
                    float(days),
                    "days",
                    {
                        "event": str(event.get("name") or event.get("title") or "Official political deadline"),
                        "eventDate": event_date,
                        "officialSourceClass": "official election/institutional calendar",
                        "marketType": "political_deadline_delay",
                        "relevance": "parser_verified_official_calendar_timing",
                    },
                )
            )
    risk = _float_value(
        event.get("deadline_delay_risk_index"),
        event.get("delay_risk_index"),
        event.get("risk_index"),
    )
    if risk is not None:
        rows.append(
            _observation(
                run_id,
                observed_at,
                "official_politics_calendar",
                "politics",
                "deadline_delay_risk_index",
                max(0.0, min(float(risk), 1.0)),
                "probability_proxy",
                {
                    "event": str(event.get("name") or event.get("title") or "Institutional deadline risk input"),
                    "officialSourceClass": "structured institutional timing input",
                    "marketType": "political_deadline_delay",
                    "relevance": "parser_verified_structured_risk_proxy",
                    "note": "Risk proxies must come from approved structured inputs; raw social chatter is not accepted.",
                },
            )
        )
    return rows


def _parse_stocks_trade_observations(*, run_id: str, observed_at: str, result: FetchResult) -> list[ExternalObservation]:
    payload = _result_payload(result)
    rows: list[ExternalObservation] = []
    event = _first_event(result, preferred_terms=("earnings", "filing", "tariff", "trade", "close"))
    event_date = _event_date(event) if event else None
    if event_date:
        days = _days_until(event_date, observed_at)
        if days is not None:
            rows.append(
                _observation(
                    run_id,
                    observed_at,
                    "official_stocks_trade_calendar",
                    "stocks_trade",
                    "event_window_days",
                    float(days),
                    "days",
                    {
                        "event": str(event.get("name") or event.get("title") or event.get("event") or "Official stocks/trade event"),
                        "eventDate": event_date,
                        "officialSourceClass": "official company/trade calendar",
                        "marketType": "equity_close_threshold",
                        "relevance": "parser_verified_event_window",
                    },
                )
            )
    market_rows = payload.get("market_data") or payload.get("prices") or payload.get("quotes") or []
    if isinstance(market_rows, dict):
        market_rows = [market_rows]
    for item in market_rows if isinstance(market_rows, list) else []:
        if not isinstance(item, dict):
            continue
        value = _float_value(item.get("return_1d"), item.get("one_day_return"), item.get("change_percent"))
        if value is None:
            continue
        rows.append(
            _observation(
                run_id,
                observed_at,
                "configured_market_data_provider",
                "stocks_trade",
                "underlying_return_1d",
                float(value),
                "return",
                {
                    "instrument": str(item.get("symbol") or item.get("ticker") or "structured market-data input"),
                    "marketType": "equity_close_threshold",
                    "relevance": "parser_verified_market_data",
                    "sourcePolicy": "approved_public_or_configured_provider_only",
                },
            )
        )
        break
    return rows


def _result_payload(result: FetchResult) -> dict[str, Any]:
    payload = result.get("json")
    if isinstance(payload, dict):
        return payload
    text = _result_text(result)
    if text.strip().startswith("{"):
        try:
            import json

            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _result_text(result: FetchResult) -> str:
    for key in ("text", "body", "content"):
        value = result.get(key)
        if isinstance(value, bytes):
            return _decode_body(value)
        if isinstance(value, str):
            return value
    return ""


def _first_event(result: FetchResult, *, preferred_terms: tuple[str, ...]) -> dict[str, Any] | None:
    payload = _result_payload(result)
    events = payload.get("events") or payload.get("releases") or payload.get("calendar") or []
    if isinstance(events, dict):
        events = [events]
    candidates = [row for row in events if isinstance(row, dict)] if isinstance(events, list) else []
    if not candidates:
        return None
    for event in candidates:
        text = " ".join(str(event.get(key) or "") for key in ("name", "title", "event", "description")).lower()
        if any(term in text for term in preferred_terms):
            return event
    return candidates[0]


def _event_date(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    for key in ("date", "release_date", "scheduled_at", "scheduledFor", "eventDate", "deadline"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            match = _first_iso_date(value)
            return match or value.strip()
    return None


def _first_iso_date(text: str) -> str | None:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return match.group(1) if match else None


def _days_until(event_date: str, observed_at: str) -> int | None:
    event_dt = _parse_date(event_date)
    observed_dt = _parse_date(observed_at)
    if event_dt is None or observed_dt is None:
        return None
    return max((event_dt.date() - observed_dt.date()).days, 0)


def _parse_date(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{text}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _float_value(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _observation(
    run_id: str,
    observed_at: str,
    source_id: str,
    category: str,
    metric_name: str,
    metric_value: float,
    unit: str,
    payload: dict[str, object],
) -> ExternalObservation:
    return ExternalObservation(
        observation_id=stable_id(run_id, source_id, category, metric_name, observed_at),
        source_id=source_id,
        category=category,
        observed_at=observed_at,
        as_of=observed_at,
        metric_name=metric_name,
        metric_value=metric_value,
        unit=unit,
        payload=payload,
    )
