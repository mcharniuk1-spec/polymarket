from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .migrations import MILESTONE1_POSTGRES_SQL


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

    def list_json(self, prefix: str) -> list[dict[str, Any]]:
        if not self.local_enabled:
            return []
        root = self._local_path(prefix)
        if root.is_file() and root.suffix == ".json":
            paths = [root]
        elif root.is_dir():
            paths = sorted(root.rglob("*.json"))
        else:
            return []
        rows = []
        for path in paths:
            try:
                rows.append(
                    {
                        "key": path.relative_to(self.local_root).as_posix(),
                        "payload": json.loads(path.read_text(encoding="utf-8")),
                    }
                )
            except (OSError, json.JSONDecodeError):
                continue
        return rows

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
                "error": self._safe_error(exc),
            }

    def list_json(self, prefix: str) -> list[dict[str, Any]]:
        state_prefix = self._state_key(prefix).rstrip("/")
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        select state_key, payload
                        from pipeline_state
                        where state_key = %s or state_key like %s
                        order by updated_at asc, state_key asc
                        """,
                        (state_prefix, f"{state_prefix}/%"),
                    )
                    return [
                        {
                            "key": str(row[0]).removeprefix(f"{self.prefix}/"),
                            "payload": row[1],
                        }
                        for row in cur.fetchall()
                    ]
        except Exception:
            return []

    def _state_key(self, key: str) -> str:
        return f"{self.prefix}/{key.strip('/')}"

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on deployment deps
            raise RuntimeError("PostgreSQL storage requires psycopg. Install requirements.txt.") from exc
        return psycopg.connect(self.database_url, autocommit=False)

    def apply_schema_migration(
        self,
        *,
        migration_id: str,
        sql: str,
        required_tables: list[str],
    ) -> dict[str, Any]:
        """Apply and verify a SQL migration without exposing connection details."""

        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        create table if not exists schema_migrations (
                            migration_id text primary key,
                            checksum text not null,
                            applied_at timestamptz not null default now(),
                            payload jsonb not null default '{}'::jsonb
                        )
                        """
                    )
                    cur.execute(sql)
                    cur.execute(
                        """
                        insert into schema_migrations(migration_id, checksum, payload)
                        values (%s, %s, %s::jsonb)
                        on conflict (migration_id) do update set
                            checksum = excluded.checksum,
                            applied_at = now(),
                            payload = excluded.payload
                        """,
                        (
                            migration_id,
                            checksum,
                            json.dumps(
                                {
                                    "source": "sports_edge.cli migrate",
                                    "requiredTables": required_tables,
                                    "researchOnly": True,
                                    "paperTradingOnly": True,
                                },
                                sort_keys=True,
                            ),
                        ),
                    )
                    existing_tables = self._existing_tables(cur, required_tables)
                conn.commit()
            missing_tables = sorted(set(required_tables) - set(existing_tables))
            return {
                "ok": not missing_tables,
                "migrationId": migration_id,
                "checksum": checksum,
                "storageMode": "postgres",
                "durable": not missing_tables,
                "applied": True,
                "verifiedTables": sorted(existing_tables),
                "missingTables": missing_tables,
            }
        except Exception as exc:
            return {
                "ok": False,
                "migrationId": migration_id,
                "checksum": checksum,
                "storageMode": "postgres",
                "durable": False,
                "applied": False,
                "verifiedTables": [],
                "missingTables": sorted(required_tables),
                "error": self._safe_error(exc),
            }

    def _existing_tables(self, cur: Any, required_tables: list[str]) -> list[str]:
        existing = []
        for table in required_tables:
            cur.execute(
                """
                select exists (
                    select 1
                    from information_schema.tables
                    where table_schema = 'public' and table_name = %s
                )
                """,
                (table,),
            )
            row = cur.fetchone()
            if row and bool(row[0]):
                existing.append(table)
        return existing

    def _safe_error(self, exc: Exception) -> str:
        message = str(exc)
        if self.database_url:
            message = message.replace(self.database_url, "<masked database url>")
        for key in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING"):
            value = os.environ.get(key)
            if value:
                message = message.replace(value, f"<masked {key}>")
        return message

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
            cur.execute(MILESTONE1_POSTGRES_SQL)

    def _project_payload(self, conn: Any, key: str, payload: Any) -> None:
        if key.startswith("collection_runs/") and isinstance(payload, dict):
            self._project_collection_run(conn, payload)
        elif key.startswith("collector_runs/") and isinstance(payload, dict):
            self._project_collector_run(conn, payload)
        elif key.startswith("cron_runs/") and isinstance(payload, dict):
            self._project_cron_run(conn, payload)
            if "contextReports" in payload or "decisionSignals" in payload:
                self._project_daily_run(conn, payload)
        elif key == "model_state.json" and isinstance(payload, dict):
            self._project_model_metrics(conn, payload)

    def _project_cron_run(self, conn: Any, payload: dict[str, Any]) -> None:
        cron = payload.get("cronRun", payload)
        run_id = str(cron.get("run_id") or "")
        if not run_id:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into cron_runs(
                    run_id, cycle_type, scheduled_for, idempotency_key, status, dry_run,
                    started_at, finished_at, counts, warnings, errors, payload, updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, now())
                on conflict (run_id) do update set
                    cycle_type = excluded.cycle_type,
                    scheduled_for = excluded.scheduled_for,
                    idempotency_key = excluded.idempotency_key,
                    status = excluded.status,
                    dry_run = excluded.dry_run,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    counts = excluded.counts,
                    warnings = excluded.warnings,
                    errors = excluded.errors,
                    payload = excluded.payload,
                    updated_at = now()
                """,
                (
                    run_id,
                    cron.get("cycle_type"),
                    _null_if_blank(cron.get("scheduled_for")),
                    cron.get("idempotency_key"),
                    cron.get("status"),
                    bool(cron.get("dry_run")),
                    _null_if_blank(cron.get("started_at")),
                    _null_if_blank(cron.get("finished_at")),
                    json.dumps(cron.get("counts", {}), sort_keys=True),
                    json.dumps(cron.get("warnings", []), sort_keys=True),
                    json.dumps(cron.get("errors", []), sort_keys=True),
                    json.dumps(payload, sort_keys=True),
                ),
            )

    def _project_collector_run(self, conn: Any, payload: dict[str, Any]) -> None:
        data_agent = payload.get("dataAgent", {})
        run_id = str(data_agent.get("runId") or payload.get("cronRun", {}).get("run_id") or "")
        if not run_id:
            return
        self._project_cron_run(conn, payload)
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
                    _null_if_blank(payload.get("cronRun", {}).get("started_at") or data_agent.get("observedAt")),
                    _null_if_blank(payload.get("cronRun", {}).get("finished_at") or data_agent.get("observedAt")),
                    payload.get("cronRun", {}).get("cycle_type"),
                    payload.get("sourceMode") or data_agent.get("sourceMode"),
                    payload.get("targetCount"),
                    payload.get("cronRun", {}).get("status"),
                    bool((payload.get("sourceMode") or data_agent.get("sourceMode")) == "live"),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            for source in data_agent.get("sourceRecords", []):
                self._project_external_source_record(cur, source)
            for market in data_agent.get("marketSnapshots", []):
                self._project_market_snapshot(cur, run_id, market)
            for book in data_agent.get("orderBookSnapshots", []):
                self._project_order_book_snapshot(cur, run_id, book)
            for observation in data_agent.get("externalObservations", []):
                self._project_external_observation(cur, observation)

    def _project_daily_run(self, conn: Any, payload: dict[str, Any]) -> None:
        data_agent = payload.get("dataAgent", {})
        cron = payload.get("cronRun", {})
        run_id = str(cron.get("run_id") or data_agent.get("runId") or "")
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
                    _null_if_blank(cron.get("started_at") or data_agent.get("observedAt")),
                    _null_if_blank(cron.get("finished_at") or data_agent.get("observedAt")),
                    cron.get("cycle_type"),
                    payload.get("sourceMode") or data_agent.get("sourceMode"),
                    payload.get("targetCount"),
                    cron.get("status"),
                    bool((payload.get("sourceMode") or data_agent.get("sourceMode")) == "live"),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            for source in data_agent.get("sourceRecords", payload.get("sourceRecords", [])):
                self._project_external_source_record(cur, source)
            for market in data_agent.get("marketSnapshots", []):
                self._project_market_snapshot(cur, run_id, market)
            for book in data_agent.get("orderBookSnapshots", []):
                self._project_order_book_snapshot(cur, run_id, book)
            for observation in data_agent.get("externalObservations", []):
                self._project_external_observation(cur, observation)
            for report in payload.get("contextReports", []):
                self._project_context_report(cur, report)
            for output in payload.get("modelOutputs", []):
                self._project_model_output(cur, output)
            for decision in payload.get("decisionSignals", []):
                self._project_decision_signal(cur, decision)
                if decision.get("decision") == "paper_bet":
                    self._project_paper_bet(cur, decision, payload.get("modelOutputs", []))
            for outcome in payload.get("resolvedOutcomes", []):
                self._project_resolved_outcome(cur, outcome)
            for note in payload.get("decisionNotes", []):
                self._project_decision_note(cur, note)
            for lesson in payload.get("knowledgeLessons", []):
                self._project_knowledge_lesson(cur, lesson)
            portfolio = payload.get("portfolioState")
            if isinstance(portfolio, dict):
                self._project_portfolio_snapshot(cur, portfolio)

    def _project_external_source_record(self, cur: Any, source: dict[str, Any]) -> None:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            return
        cur.execute(
            """
            insert into external_source_records(
                source_id, name, source_type, category, reliability_tier, access_policy,
                freshness_sla_minutes, url, notes, payload, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
            on conflict (source_id) do update set
                name = excluded.name,
                source_type = excluded.source_type,
                category = excluded.category,
                reliability_tier = excluded.reliability_tier,
                access_policy = excluded.access_policy,
                freshness_sla_minutes = excluded.freshness_sla_minutes,
                url = excluded.url,
                notes = excluded.notes,
                payload = excluded.payload,
                updated_at = now()
            """,
            (
                source_id,
                source.get("name"),
                source.get("source_type"),
                source.get("category"),
                source.get("reliability_tier"),
                source.get("access_policy"),
                source.get("freshness_sla_minutes"),
                source.get("url"),
                source.get("notes"),
                json.dumps(source, sort_keys=True),
            ),
        )

    def _project_market_snapshot(self, cur: Any, run_id: str, market: dict[str, Any]) -> None:
        market_id = str(market.get("market_id") or "")
        snapshot_id = str(market.get("snapshot_id") or _stable_id(f"{run_id}:{market_id}"))
        if not market_id:
            return
        current_probability = None
        prices = market.get("outcome_prices")
        if isinstance(prices, list) and prices:
            current_probability = prices[0]
        cur.execute(
            """
            insert into market_snapshots(
                snapshot_id, run_id, market_id, category, market_title, source_url,
                expected_resolution_at, current_probability, spread, liquidity, volume_24h,
                observed_at, condition_id, active, closed, outcomes, outcome_prices, fetched_at,
                rules_summary, resolution_criteria, time_to_resolution_hours, raw_ref, payload
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb
            )
            on conflict (run_id, market_id) do update set
                category = excluded.category,
                market_title = excluded.market_title,
                source_url = excluded.source_url,
                expected_resolution_at = excluded.expected_resolution_at,
                current_probability = excluded.current_probability,
                spread = excluded.spread,
                liquidity = excluded.liquidity,
                volume_24h = excluded.volume_24h,
                observed_at = excluded.observed_at,
                condition_id = excluded.condition_id,
                active = excluded.active,
                closed = excluded.closed,
                outcomes = excluded.outcomes,
                outcome_prices = excluded.outcome_prices,
                fetched_at = excluded.fetched_at,
                rules_summary = excluded.rules_summary,
                resolution_criteria = excluded.resolution_criteria,
                time_to_resolution_hours = excluded.time_to_resolution_hours,
                raw_ref = excluded.raw_ref,
                payload = excluded.payload
            """,
            (
                snapshot_id,
                run_id,
                market_id,
                market.get("category"),
                market.get("question"),
                market.get("source_url"),
                _null_if_blank(market.get("end_time")),
                current_probability,
                market.get("spread"),
                market.get("liquidity"),
                market.get("volume_24h"),
                _null_if_blank(market.get("observed_at")),
                market.get("condition_id"),
                market.get("active"),
                market.get("closed"),
                json.dumps(market.get("outcomes", []), sort_keys=True),
                json.dumps(market.get("outcome_prices", []), sort_keys=True),
                _null_if_blank(market.get("fetched_at")),
                market.get("rules_summary"),
                market.get("resolution_criteria"),
                market.get("time_to_resolution_hours"),
                market.get("raw_ref"),
                json.dumps(market, sort_keys=True),
            ),
        )

    def _project_order_book_snapshot(self, cur: Any, run_id: str, book: dict[str, Any]) -> None:
        snapshot_id = str(book.get("snapshot_id") or "")
        if not snapshot_id:
            return
        cur.execute(
            """
            insert into order_book_snapshots(
                snapshot_id, run_id, market_id, token_id, observed_at, best_bid, best_ask,
                spread, bid_depth, ask_depth, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (market_id, token_id, observed_at) do update set
                best_bid = excluded.best_bid,
                best_ask = excluded.best_ask,
                spread = excluded.spread,
                bid_depth = excluded.bid_depth,
                ask_depth = excluded.ask_depth,
                payload = excluded.payload
            """,
            (
                snapshot_id,
                run_id,
                book.get("market_id"),
                book.get("token_id"),
                _null_if_blank(book.get("observed_at")),
                book.get("best_bid"),
                book.get("best_ask"),
                book.get("spread"),
                book.get("bid_depth"),
                book.get("ask_depth"),
                json.dumps(book, sort_keys=True),
            ),
        )

    def _project_external_observation(self, cur: Any, observation: dict[str, Any]) -> None:
        observation_id = str(observation.get("observation_id") or "")
        if not observation_id:
            return
        cur.execute(
            """
            insert into external_observations(
                observation_id, source_id, category, observed_at, as_of,
                metric_name, metric_value, unit, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (source_id, category, metric_name, observed_at) do update set
                metric_value = excluded.metric_value,
                unit = excluded.unit,
                payload = excluded.payload
            """,
            (
                observation_id,
                observation.get("source_id"),
                observation.get("category"),
                _null_if_blank(observation.get("observed_at")),
                _null_if_blank(observation.get("as_of")),
                observation.get("metric_name"),
                observation.get("metric_value"),
                observation.get("unit"),
                json.dumps(observation, sort_keys=True),
            ),
        )

    def _project_context_report(self, cur: Any, report: dict[str, Any]) -> None:
        report_id = str(report.get("report_id") or "")
        if not report_id:
            return
        cur.execute(
            """
            insert into context_reports(
                report_id, run_id, category, scope, candidate_id, created_at,
                confidence, reliability, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (report_id) do update set
                confidence = excluded.confidence,
                reliability = excluded.reliability,
                payload = excluded.payload
            """,
            (
                report_id,
                report.get("run_id"),
                report.get("category"),
                report.get("scope"),
                report.get("candidate_id"),
                _null_if_blank(report.get("created_at")),
                report.get("confidence"),
                report.get("reliability"),
                json.dumps(report, sort_keys=True),
            ),
        )

    def _project_model_output(self, cur: Any, output: dict[str, Any]) -> None:
        output_id = str(output.get("output_id") or "")
        if not output_id:
            return
        cur.execute(
            """
            insert into model_outputs(
                output_id, run_id, candidate_id, market_id, category, model_family,
                probability, confidence, evidence_quality, created_at, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (run_id, candidate_id, model_family) do update set
                probability = excluded.probability,
                confidence = excluded.confidence,
                evidence_quality = excluded.evidence_quality,
                payload = excluded.payload
            """,
            (
                output_id,
                output.get("run_id"),
                output.get("candidate_id"),
                output.get("market_id"),
                output.get("category"),
                output.get("model_family"),
                output.get("probability"),
                output.get("confidence"),
                output.get("evidence_quality"),
                _null_if_blank(output.get("created_at")),
                json.dumps(output, sort_keys=True),
            ),
        )

    def _project_decision_signal(self, cur: Any, decision: dict[str, Any]) -> None:
        decision_id = str(decision.get("decision_id") or "")
        if not decision_id:
            return
        cur.execute(
            """
            insert into decision_signals(
                decision_id, run_id, candidate_id, market_id, category, decision,
                confidence, reliability, edge, stake_units, created_at, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (run_id, candidate_id) do update set
                decision = excluded.decision,
                confidence = excluded.confidence,
                reliability = excluded.reliability,
                edge = excluded.edge,
                stake_units = excluded.stake_units,
                payload = excluded.payload
            """,
            (
                decision_id,
                decision.get("run_id"),
                decision.get("candidate_id"),
                decision.get("market_id"),
                decision.get("category"),
                decision.get("decision"),
                decision.get("confidence"),
                decision.get("reliability"),
                decision.get("edge"),
                decision.get("stake_units"),
                _null_if_blank(decision.get("created_at")),
                json.dumps(decision, sort_keys=True),
            ),
        )

    def _project_paper_bet(self, cur: Any, decision: dict[str, Any], model_outputs: list[dict[str, Any]]) -> None:
        decision_id = str(decision.get("decision_id") or "")
        market_price = _market_implied_price(decision.get("candidate_id"), model_outputs)
        paper_bet_id = _stable_id(f"{decision_id}:yes")
        cur.execute(
            """
            insert into paper_bets(
                paper_bet_id, decision_id, run_id, candidate_id, market_id, category,
                side, entry_price, stake_units, slippage_assumption, status, opened_at, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (run_id, candidate_id, side) do update set
                entry_price = excluded.entry_price,
                stake_units = excluded.stake_units,
                status = excluded.status,
                payload = excluded.payload
            """,
            (
                paper_bet_id,
                decision_id,
                decision.get("run_id"),
                decision.get("candidate_id"),
                decision.get("market_id"),
                decision.get("category"),
                "Yes",
                market_price,
                decision.get("stake_units"),
                0.01,
                "open",
                _null_if_blank(decision.get("created_at")),
                json.dumps({"decision": decision, "entryPriceSource": "market_implied_probability"}, sort_keys=True),
            ),
        )

    def _project_portfolio_snapshot(self, cur: Any, portfolio: dict[str, Any]) -> None:
        portfolio_id = str(portfolio.get("portfolio_id") or "")
        if not portfolio_id:
            return
        cur.execute(
            """
            insert into portfolio_snapshots(
                portfolio_id, run_id, bankroll_units, total_exposure_units,
                current_drawdown_pct, created_at, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (run_id) do update set
                bankroll_units = excluded.bankroll_units,
                total_exposure_units = excluded.total_exposure_units,
                current_drawdown_pct = excluded.current_drawdown_pct,
                payload = excluded.payload
            """,
            (
                portfolio_id,
                portfolio.get("run_id"),
                portfolio.get("bankroll_units"),
                portfolio.get("total_exposure_units"),
                portfolio.get("current_drawdown_pct"),
                _null_if_blank(portfolio.get("created_at")),
                json.dumps(portfolio, sort_keys=True),
            ),
        )

    def _project_resolved_outcome(self, cur: Any, outcome: dict[str, Any]) -> None:
        outcome_id = str(outcome.get("outcome_id") or "")
        if not outcome_id:
            return
        cur.execute(
            """
            insert into resolved_outcomes(
                outcome_id, paper_bet_id, market_id, resolved_at, result,
                proof_url, pnl_units, calibration_bucket, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (outcome_id) do update set
                result = excluded.result,
                proof_url = excluded.proof_url,
                pnl_units = excluded.pnl_units,
                calibration_bucket = excluded.calibration_bucket,
                payload = excluded.payload
            """,
            (
                outcome_id,
                outcome.get("paper_bet_id"),
                outcome.get("market_id"),
                _null_if_blank(outcome.get("resolved_at")),
                outcome.get("result"),
                outcome.get("proof_url"),
                outcome.get("pnl_units"),
                outcome.get("calibration_bucket"),
                json.dumps(outcome, sort_keys=True),
            ),
        )

    def _project_decision_note(self, cur: Any, note: dict[str, Any]) -> None:
        note_id = str(note.get("note_id") or "")
        if not note_id:
            return
        cur.execute(
            """
            insert into decision_notes(
                note_id, decision_id, run_id, candidate_id, created_at, summary, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (note_id) do update set
                summary = excluded.summary,
                payload = excluded.payload
            """,
            (
                note_id,
                note.get("decision_id"),
                note.get("run_id"),
                note.get("candidate_id"),
                _null_if_blank(note.get("created_at")),
                note.get("summary"),
                json.dumps(note, sort_keys=True),
            ),
        )

    def _project_knowledge_lesson(self, cur: Any, lesson: dict[str, Any]) -> None:
        lesson_id = str(lesson.get("lesson_id") or "")
        if not lesson_id:
            return
        cur.execute(
            """
            insert into knowledge_lessons(
                lesson_id, category, lesson_type, created_at, source_run_id,
                severity, summary, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (lesson_id) do update set
                severity = excluded.severity,
                summary = excluded.summary,
                payload = excluded.payload
            """,
            (
                lesson_id,
                lesson.get("category"),
                lesson.get("lesson_type"),
                _null_if_blank(lesson.get("created_at")),
                lesson.get("source_run_id"),
                lesson.get("severity"),
                lesson.get("summary"),
                json.dumps(lesson, sort_keys=True),
            ),
        )

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


def _market_implied_price(candidate_id: Any, model_outputs: list[dict[str, Any]]) -> Any:
    for output in model_outputs:
        if output.get("candidate_id") == candidate_id and output.get("model_family") == "market_implied_probability":
            return output.get("probability")
    return None
