from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_STATE_DIR = REPO_ROOT / "data" / "generated" / "production_state"
DEFAULT_PREFIX = "polymarket/state"


def configured_database_url() -> str | None:
    for key in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING"):
        value = os.environ.get(key)
        if value:
            return value
    return None


class JsonStateStore:
    """Small JSON state store with local fallback and optional Vercel Blob mirroring."""

    def __init__(self, local_root: Path | str = LOCAL_STATE_DIR, prefix: str | None = None) -> None:
        self.local_root = Path(local_root)
        self.prefix = (prefix or os.environ.get("POLYMARKET_STATE_PREFIX") or DEFAULT_PREFIX).strip("/")
        self.token = os.environ.get("BLOB_READ_WRITE_TOKEN")
        self.local_enabled = not (os.environ.get("VERCEL") or str(REPO_ROOT).startswith("/var/task"))
        self.storage_mode = "vercel_blob" if self.token else "local_file"

    def read_json(self, key: str, default: Any = None) -> Any:
        local_path = self._local_path(key)
        if self.token:
            remote = self._read_blob_json(key)
            if remote is not None:
                return remote
        if self.local_enabled and local_path.exists():
            return json.loads(local_path.read_text(encoding="utf-8"))
        return default

    def write_json(self, key: str, payload: Any) -> dict[str, Any]:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        local_path = self._local_path(key)
        if self.token:
            blob_result = self._write_blob(key, encoded)
            if blob_result.get("durable"):
                return {"key": key, "localPath": None, **blob_result}
            if not self.local_enabled:
                return {"key": key, "localPath": None, **blob_result}
        if not self.local_enabled:
            return {
                "key": key,
                "localPath": None,
                "storageMode": "unavailable",
                "durable": False,
                "blobMirrored": False,
                "error": "Vercel production state requires BLOB_READ_WRITE_TOKEN.",
            }
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(encoded)
        return {
            "key": key,
            "localPath": str(local_path),
            "storageMode": "local_file",
            "durable": False,
            "blobMirrored": False,
        }

    def _local_path(self, key: str) -> Path:
        safe_key = key.strip("/").replace("..", "_")
        return self.local_root / safe_key

    def _blob_path(self, key: str) -> str:
        return f"{self.prefix}/{key.strip('/')}"

    def _write_blob(self, key: str, encoded: bytes) -> dict[str, Any]:
        try:
            response = self._blob_api_request(
                "PUT",
                f"/?{urlencode({'pathname': self._blob_path(key)})}",
                body=encoded,
                extra_headers={
                    "x-vercel-blob-access": "private",
                    "x-add-random-suffix": "0",
                    "x-allow-overwrite": "1",
                    "x-content-type": "application/json",
                },
            )
            return {
                "storageMode": "vercel_blob",
                "durable": True,
                "blobMirrored": True,
                "blob": response,
            }
        except Exception as exc:  # pragma: no cover - depends on deployed Vercel Blob runtime
            return {
                "storageMode": "local_file",
                "durable": False,
                "blobMirrored": False,
                "blobError": str(exc),
            }

    def _read_blob_json(self, key: str) -> Any | None:
        try:
            listing = self._blob_api_request(
                "GET",
                f"?{urlencode({'prefix': self._blob_path(key), 'limit': '10'})}",
            )
            blobs = listing.get("blobs", []) if isinstance(listing, dict) else []
            exact = [row for row in blobs if row.get("pathname") == self._blob_path(key)]
            if not exact:
                return None
            url = exact[0].get("downloadUrl") or exact[0].get("url")
            if not url:
                return None
            request = Request(url, headers={"Authorization": f"Bearer {self.token}"})
            with urlopen(request, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

    def _blob_api_request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("BLOB_READ_WRITE_TOKEN is not configured.")
        store_id = self._blob_store_id()
        request = Request(
            f"https://vercel.com/api/blob{path}",
            data=body,
            method=method,
            headers={
                "authorization": f"Bearer {self.token}",
                "x-api-version": "12",
                "x-api-blob-request-attempt": "0",
                "x-api-blob-request-id": f"{store_id}:{int(time.time() * 1000)}",
                "x-vercel-blob-store-id": store_id,
                **(extra_headers or {}),
            },
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _blob_store_id(self) -> str:
        explicit = os.environ.get("BLOB_STORE_ID")
        if explicit:
            return explicit.removeprefix("store_")
        parts = self.token.split("_") if self.token else []
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        raise RuntimeError("Unable to derive Vercel Blob store id from token.")


def default_store() -> JsonStateStore:
    database_url = configured_database_url()
    if database_url:
        return PostgresStateStore(database_url=database_url)
    return JsonStateStore()


class PostgresStateStore(JsonStateStore):
    """PostgreSQL-backed JSON state store plus queryable market projections."""

    def __init__(self, database_url: str, prefix: str | None = None) -> None:
        super().__init__(local_root=LOCAL_STATE_DIR, prefix=prefix)
        self.database_url = database_url
        self.storage_mode = "postgres"
        self.local_enabled = False

    def read_json(self, key: str, default: Any = None) -> Any:
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "select payload from pipeline_state where state_key = %s",
                        (self._state_key(key),),
                    )
                    row = cur.fetchone()
                    return row[0] if row else default
        except Exception:
            return default

    def write_json(self, key: str, payload: Any) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into pipeline_state(state_key, payload, updated_at)
                        values (%s, %s::jsonb, now())
                        on conflict (state_key) do update
                        set payload = excluded.payload, updated_at = now()
                        """,
                        (self._state_key(key), json.dumps(payload, sort_keys=True)),
                    )
                self._project_payload(conn, key, payload)
                conn.commit()
            return {
                "key": key,
                "localPath": None,
                "storageMode": "postgres",
                "durable": True,
                "blobMirrored": False,
            }
        except Exception as exc:
            return {
                "key": key,
                "localPath": None,
                "storageMode": "postgres",
                "durable": False,
                "blobMirrored": False,
                "error": str(exc),
            }

    def _state_key(self, key: str) -> str:
        return f"{self.prefix}/{key.strip('/')}"

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on deployment deps
            raise RuntimeError("PostgreSQL storage requires psycopg. Install requirements.txt.") from exc
        return psycopg.connect(self.database_url, autocommit=False)

    def _ensure_schema(self, conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists pipeline_state (
                    state_key text primary key,
                    payload jsonb not null,
                    updated_at timestamptz not null default now()
                );
                create table if not exists collection_runs (
                    run_id text primary key,
                    cycle_started_at timestamptz,
                    created_at timestamptz,
                    cycle_type text,
                    source_mode text,
                    target_count integer,
                    status text,
                    live_data_confirmed boolean not null default false,
                    payload jsonb not null
                );
                create table if not exists market_snapshots (
                    snapshot_id text primary key,
                    run_id text not null references collection_runs(run_id) on delete cascade,
                    market_id text not null,
                    event_id text,
                    category text,
                    subcategory text,
                    market_title text,
                    outcome text,
                    source_url text,
                    published_at timestamptz,
                    gathered_at timestamptz,
                    decision_at timestamptz,
                    expected_resolution_at timestamptz,
                    current_probability double precision,
                    spread double precision,
                    liquidity double precision,
                    volume_24h double precision,
                    decision text,
                    stake_units double precision,
                    confidence double precision,
                    expected_value double precision,
                    forecast_probability double precision,
                    payload jsonb not null,
                    unique (run_id, market_id)
                );
                create index if not exists idx_market_snapshots_newest
                    on market_snapshots (published_at desc nulls last, gathered_at desc);
                create index if not exists idx_market_snapshots_category
                    on market_snapshots (category, published_at desc nulls last);
                create table if not exists market_news_items (
                    news_id text primary key,
                    snapshot_id text not null references market_snapshots(snapshot_id) on delete cascade,
                    market_id text not null,
                    source text,
                    source_url text,
                    title text,
                    publication_time timestamptz,
                    fetched_time timestamptz,
                    reliability_tier integer,
                    relevance_score double precision,
                    payload jsonb not null
                );
                create table if not exists model_metric_snapshots (
                    metric_id text primary key,
                    run_id text,
                    scope text,
                    sample_count integer,
                    labeled_example_count integer,
                    brier double precision,
                    payload jsonb not null
                );
                """
            )

    def _project_payload(self, conn: Any, key: str, payload: Any) -> None:
        if key.startswith("collection_runs/") and isinstance(payload, dict):
            self._project_collection_run(conn, payload)
        elif key == "model_state.json" and isinstance(payload, dict):
            self._project_model_metrics(conn, payload)

    def _project_collection_run(self, conn: Any, snapshot: dict[str, Any]) -> None:
        run_id = str(snapshot.get("id") or "")
        if not run_id:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into collection_runs(
                    run_id, cycle_started_at, created_at, cycle_type, source_mode,
                    target_count, status, live_data_confirmed, payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (run_id) do update set
                    cycle_started_at = excluded.cycle_started_at,
                    created_at = excluded.created_at,
                    cycle_type = excluded.cycle_type,
                    source_mode = excluded.source_mode,
                    target_count = excluded.target_count,
                    status = excluded.status,
                    live_data_confirmed = excluded.live_data_confirmed,
                    payload = excluded.payload
                """,
                (
                    run_id,
                    _null_if_blank(snapshot.get("cycleStartedAt")),
                    _null_if_blank(snapshot.get("createdAt")),
                    snapshot.get("cycleType"),
                    snapshot.get("sourceMode"),
                    snapshot.get("targetCount"),
                    snapshot.get("status"),
                    bool(snapshot.get("liveDataConfirmed")),
                    json.dumps(snapshot, sort_keys=True),
                ),
            )
            recommendations = snapshot.get("dashboard", {}).get("multi_agent", {}).get("recommendations", [])
            analyses = {
                row.get("marketSlug") or row.get("marketId"): row
                for row in snapshot.get("intelligence", {}).get("marketAnalysisResults", [])
            }
            for item in recommendations:
                candidate = item.get("candidate", {})
                market_id = str(candidate.get("candidate_id") or "")
                if not market_id:
                    continue
                analysis = analyses.get(market_id, {})
                lifecycle = analysis.get("lifecycleTimes", {})
                forecast = analysis.get("multiModelForecast", {})
                snapshot_id = _stable_id(f"{run_id}:{market_id}")
                cur.execute(
                    """
                    insert into market_snapshots(
                        snapshot_id, run_id, market_id, event_id, category, subcategory,
                        market_title, outcome, source_url, published_at, gathered_at,
                        decision_at, expected_resolution_at, current_probability, spread,
                        liquidity, volume_24h, decision, stake_units, confidence,
                        expected_value, forecast_probability, payload
                    )
                    values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    on conflict (run_id, market_id) do update set
                        category = excluded.category,
                        market_title = excluded.market_title,
                        published_at = excluded.published_at,
                        gathered_at = excluded.gathered_at,
                        decision_at = excluded.decision_at,
                        expected_resolution_at = excluded.expected_resolution_at,
                        current_probability = excluded.current_probability,
                        spread = excluded.spread,
                        liquidity = excluded.liquidity,
                        volume_24h = excluded.volume_24h,
                        decision = excluded.decision,
                        stake_units = excluded.stake_units,
                        confidence = excluded.confidence,
                        expected_value = excluded.expected_value,
                        forecast_probability = excluded.forecast_probability,
                        payload = excluded.payload
                    """,
                    (
                        snapshot_id,
                        run_id,
                        market_id,
                        candidate.get("event_id"),
                        candidate.get("category"),
                        candidate.get("subcategory"),
                        candidate.get("market_title"),
                        candidate.get("outcome"),
                        candidate.get("source_url"),
                        _null_if_blank(candidate.get("published_at") or candidate.get("updated_at")),
                        _null_if_blank(lifecycle.get("gatheredAt") or snapshot.get("cycleStartedAt")),
                        _null_if_blank(lifecycle.get("estimatedDecisionAt") or analysis.get("createdAt")),
                        _null_if_blank(lifecycle.get("expectedResolutionAt") or candidate.get("end_time")),
                        candidate.get("price"),
                        candidate.get("spread"),
                        candidate.get("liquidity"),
                        candidate.get("volume_24h"),
                        item.get("decision"),
                        item.get("stake_units"),
                        item.get("confidence"),
                        item.get("expected_value"),
                        forecast.get("ensembleProbability"),
                        json.dumps({"recommendation": item, "analysis": analysis}, sort_keys=True),
                    ),
                )
                self._project_news_items(cur, snapshot_id, market_id, analysis)

    def _project_news_items(self, cur: Any, snapshot_id: str, market_id: str, analysis: dict[str, Any]) -> None:
        for index, item in enumerate(analysis.get("newsContext", {}).get("items", [])):
            news_id = _stable_id(f"{snapshot_id}:news:{index}:{item.get('title')}:{item.get('source')}")
            cur.execute(
                """
                insert into market_news_items(
                    news_id, snapshot_id, market_id, source, source_url, title,
                    publication_time, fetched_time, reliability_tier, relevance_score, payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (news_id) do update set
                    source = excluded.source,
                    source_url = excluded.source_url,
                    title = excluded.title,
                    publication_time = excluded.publication_time,
                    fetched_time = excluded.fetched_time,
                    reliability_tier = excluded.reliability_tier,
                    relevance_score = excluded.relevance_score,
                    payload = excluded.payload
                """,
                (
                    news_id,
                    snapshot_id,
                    market_id,
                    item.get("source"),
                    item.get("sourceUrl"),
                    item.get("title"),
                    _null_if_blank(item.get("publicationTime")),
                    _null_if_blank(item.get("fetchedTime")),
                    item.get("reliabilityTier"),
                    item.get("relevanceScore"),
                    json.dumps(item, sort_keys=True),
                ),
            )

    def _project_model_metrics(self, conn: Any, payload: dict[str, Any]) -> None:
        with conn.cursor() as cur:
            for row in payload.get("health", []):
                metric_id = _stable_id(f"{payload.get('updatedAt')}:{row.get('scope')}")
                cur.execute(
                    """
                    insert into model_metric_snapshots(
                        metric_id, run_id, scope, sample_count, labeled_example_count, brier, payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    on conflict (metric_id) do update set
                        sample_count = excluded.sample_count,
                        labeled_example_count = excluded.labeled_example_count,
                        brier = excluded.brier,
                        payload = excluded.payload
                    """,
                    (
                        metric_id,
                        payload.get("updatedAt"),
                        row.get("scope"),
                        row.get("sampleCount"),
                        row.get("labeledExampleCount"),
                        row.get("brier"),
                        json.dumps(row, sort_keys=True),
                    ),
                )


def _stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _null_if_blank(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value
