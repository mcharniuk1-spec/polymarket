from __future__ import annotations


MILESTONE1_MIGRATION_ID = "20260610_milestone1_research_contracts"

MILESTONE1_POSTGRES_SQL = """
create table if not exists cron_runs (
    run_id text primary key,
    cycle_type text not null,
    scheduled_for timestamptz not null,
    idempotency_key text not null unique,
    status text not null,
    dry_run boolean not null default false,
    started_at timestamptz not null,
    finished_at timestamptz,
    counts jsonb not null default '{}'::jsonb,
    warnings jsonb not null default '[]'::jsonb,
    errors jsonb not null default '[]'::jsonb,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists market_snapshots (
    snapshot_id text primary key,
    run_id text not null,
    market_id text not null,
    payload jsonb not null
);

alter table market_snapshots add column if not exists observed_at timestamptz;
alter table market_snapshots add column if not exists category text;
alter table market_snapshots add column if not exists market_title text;
alter table market_snapshots add column if not exists source_url text;
alter table market_snapshots add column if not exists expected_resolution_at timestamptz;
alter table market_snapshots add column if not exists current_probability double precision;
alter table market_snapshots add column if not exists spread double precision;
alter table market_snapshots add column if not exists liquidity double precision;
alter table market_snapshots add column if not exists volume_24h double precision;
alter table market_snapshots add column if not exists condition_id text;
alter table market_snapshots add column if not exists active boolean;
alter table market_snapshots add column if not exists closed boolean;
alter table market_snapshots add column if not exists outcomes jsonb;
alter table market_snapshots add column if not exists outcome_prices jsonb;
alter table market_snapshots add column if not exists fetched_at timestamptz;
alter table market_snapshots add column if not exists rules_summary text;
alter table market_snapshots add column if not exists resolution_criteria text;
alter table market_snapshots add column if not exists time_to_resolution_hours double precision;
alter table market_snapshots add column if not exists raw_ref text;

create table if not exists order_book_snapshots (
    snapshot_id text primary key,
    run_id text,
    market_id text not null,
    token_id text,
    observed_at timestamptz not null,
    best_bid double precision,
    best_ask double precision,
    spread double precision,
    bid_depth double precision,
    ask_depth double precision,
    payload jsonb not null,
    unique (market_id, token_id, observed_at)
);

create table if not exists external_source_records (
    source_id text primary key,
    name text not null,
    source_type text not null,
    category text not null,
    reliability_tier text not null,
    access_policy text not null,
    freshness_sla_minutes integer,
    url text,
    notes text,
    payload jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists external_observations (
    observation_id text primary key,
    source_id text references external_source_records(source_id) on delete set null,
    category text not null,
    observed_at timestamptz not null,
    as_of timestamptz,
    metric_name text not null,
    metric_value double precision,
    unit text,
    payload jsonb not null,
    unique (source_id, category, metric_name, observed_at)
);

create table if not exists context_reports (
    report_id text primary key,
    run_id text not null,
    category text not null,
    scope text not null,
    candidate_id text,
    created_at timestamptz not null,
    confidence double precision,
    reliability text,
    payload jsonb not null,
    unique (run_id, category, scope, candidate_id)
);

create table if not exists model_outputs (
    output_id text primary key,
    run_id text not null,
    candidate_id text not null,
    market_id text not null,
    category text not null,
    model_family text not null,
    probability double precision,
    confidence double precision,
    evidence_quality text,
    created_at timestamptz not null,
    payload jsonb not null,
    unique (run_id, candidate_id, model_family)
);

create table if not exists decision_signals (
    decision_id text primary key,
    run_id text not null,
    candidate_id text not null,
    market_id text not null,
    category text not null,
    decision text not null,
    confidence double precision,
    reliability text,
    edge double precision,
    stake_units double precision not null default 0,
    created_at timestamptz not null,
    payload jsonb not null,
    unique (run_id, candidate_id)
);

create table if not exists paper_bets (
    paper_bet_id text primary key,
    decision_id text references decision_signals(decision_id) on delete set null,
    run_id text not null,
    candidate_id text not null,
    market_id text not null,
    category text not null,
    side text not null,
    entry_price double precision,
    stake_units double precision not null,
    slippage_assumption double precision not null default 0,
    status text not null,
    opened_at timestamptz not null,
    closed_at timestamptz,
    payload jsonb not null,
    unique (run_id, candidate_id, side)
);

create table if not exists portfolio_snapshots (
    portfolio_id text primary key,
    run_id text not null,
    bankroll_units double precision not null,
    total_exposure_units double precision not null,
    current_drawdown_pct double precision not null,
    created_at timestamptz not null,
    payload jsonb not null,
    unique (run_id)
);

create table if not exists resolved_outcomes (
    outcome_id text primary key,
    paper_bet_id text references paper_bets(paper_bet_id) on delete set null,
    market_id text not null,
    resolved_at timestamptz not null,
    result text not null,
    proof_url text,
    pnl_units double precision,
    calibration_bucket text,
    payload jsonb not null,
    unique (market_id, resolved_at)
);

create table if not exists decision_notes (
    note_id text primary key,
    decision_id text references decision_signals(decision_id) on delete cascade,
    run_id text not null,
    candidate_id text not null,
    created_at timestamptz not null,
    summary text not null,
    payload jsonb not null,
    unique (decision_id)
);

create table if not exists knowledge_lessons (
    lesson_id text primary key,
    category text not null,
    lesson_type text not null,
    created_at timestamptz not null,
    source_run_id text,
    severity text,
    summary text not null,
    payload jsonb not null
);

create index if not exists idx_cron_runs_scheduled_for on cron_runs (scheduled_for desc);
create unique index if not exists idx_market_snapshots_run_market on market_snapshots (run_id, market_id);
create index if not exists idx_context_reports_run on context_reports (run_id, category);
create index if not exists idx_model_outputs_run on model_outputs (run_id, category, model_family);
create index if not exists idx_decision_signals_run on decision_signals (run_id, decision);
create index if not exists idx_paper_bets_status on paper_bets (status, opened_at desc);
"""


def migration_statements() -> list[dict[str, str]]:
    return [{"id": MILESTONE1_MIGRATION_ID, "sql": MILESTONE1_POSTGRES_SQL}]
