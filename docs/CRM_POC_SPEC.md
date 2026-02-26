# Core Concepts
- Operational store: transactional database used by operational CRM services.
- OLAP-ish workload: analytical-style queries (segmentation/rollups) running on operational data.
- Hybrid model: common cross-tenant dimensions as relational columns; tenant-defined attributes in JSONB.
- Bloat: dead tuple/index growth from repeated updates/deletes under MVCC.
- PostgreSQL extension: modular package that adds functionality (functions, data types, operators, indexes) to PostgreSQL without modifying the core engine; installed per-database with `CREATE EXTENSION`.
- Autovacuum threshold: the number of dead tuples required before autovacuum runs, calculated as `threshold + (scale_factor × live_tuples)`; lower scale factors trigger cleanup sooner on update-heavy tables.
- Dead tuple: obsolete row version created by PostgreSQL's MVCC implementation when a row is updated or deleted; must be cleaned by vacuum to reclaim storage and maintain query performance.

## 1. Purpose and Decision Context
This POC validates PostgreSQL suitability for CRM workloads where:
- profile attributes are flexible and evolve over time
- segmentation logic uses mixed relational + JSONB predicates
- consent checks and updates are latency-sensitive
- event tables drive periodic aggregations and reporting-style queries

The POC is not attempting to replace a warehouse. It validates operational DB behavior under representative load patterns.

## 1.1 Document Positioning
1. This document is the detailed implementation spec and execution reference for the standalone POC project.
2. Stakeholder-facing assumptions snapshots can be maintained separately for early DBA alignment.
3. When assumptions and implementation details differ, reconcile both documents in the same update checkpoint.

## 2. CRM Architecture Mapping (POC Coverage)
CRM has six service domains, but this POC intentionally covers a subset:

1. User Platform Service coverage:
- profile core dimensions (`profiles`)
- dynamic profile attributes (`profile_properties` JSONB)
- consent state (`consent`)

2. Messaging/Campaign coverage:
- delivery and response facts (`message_events`)
- campaign/channel rollups via SQL

3. Not modeled directly:
- full journey orchestration state
- control-plane configuration entities
- ingestion edge validation and bus internals
- analytics warehouse schemas

## 3. POC Data Model
### 3.1 `profiles`
Purpose:
- canonical profile dimensions used in common filters and joins.

Important fields:
- `tenant_id`, `profile_id`
- `status`
- `country`, `language`
- `created_at`, `updated_at`

### 3.2 `profile_properties`
Purpose:
- tenant-defined flexible properties and segmentation keys.

Important fields:
- `custom_properties` (JSONB)
- `properties_version`
- `updated_at`

Typical JSONB keys generated:
- `plan`, `vip`, `vip_level`, `segment`
- `deposit.bucket`, `deposit.last_at`
- `risk_band`, `tags`, `last_bet_at`

### 3.3 `consent`
Purpose:
- channel/purpose consent state for eligibility logic.
- version baseline for consent behavior/perf validation in this POC: PostgreSQL `16.8`.

Important fields:
- `(tenant_id, profile_id, channel, purpose)` key
- `state`, `updated_at`, `source`

### 3.4 `message_events`
Purpose:
- append-heavy event stream used for rollups and mixed complex joins.

Important fields:
- `campaign_id`, `channel`, `event_type`, `event_time`
- `attributes` (JSONB)

### 3.5 PostgreSQL Extensions Used
This POC uses two PostgreSQL extensions (see Core Concepts for definition):

1. **`pgcrypto`**
   - Provides cryptographic functions (hashing, encryption, random data generation)
   - Enabled by schema setup for PostgreSQL feature parity and optional SQL-side experiments
   - Synthetic data generation in this POC is implemented by the Python generator, not by extension functions

2. **`pg_stat_statements`**
   - Provides aggregate SQL statement statistics when extension views are queried
   - Enabled by schema setup and reset during cleanup when available
   - In load mode, `run_queries.py` can reset and capture phase-scoped snapshots into run artifacts for automated DBA handoff

### 3.6 Autovacuum Configuration
PostgreSQL uses MVCC (Multi-Version Concurrency Control), which creates dead tuples on UPDATE/DELETE operations. Autovacuum automatically cleans these dead tuples when the count exceeds: `threshold + (scale_factor × live_tuples)`.

Default PostgreSQL values: `threshold=50, scale_factor=0.2` (vacuum when dead tuples > 50 + 20% of live tuples).

This POC uses custom scale factors for update-heavy tables (see Core Concepts for autovacuum threshold definition):

| Table | Scale Factor | Fillfactor | Rationale |
|-------|--------------|------------|-----------|
| `profile_properties` | **0.02** (2%) | 75% | JSONB-heavy with frequent updates; vacuum sooner to control TOAST bloat |
| `consent` | **0.03** (3%) | 85% | Operational churn table; moderate cleanup frequency |
| `message_events` | **0.05** (5%) | default | Append-heavy; fewer dead tuples, less aggressive cleanup |
| `profiles` | **0.2** (default) | default | Not update-heavy; PostgreSQL defaults are sufficient |

These settings ensure bloat metrics and vacuum behavior align with expected workload patterns.

## 4. Dataset Strategy
Default scales:
1. Baseline: `100k profiles + 5M events`
2. Stretch: `500k profiles + 20M events`

Generation strategy:
- deterministic random seeds for reproducibility
- skewed categorical distributions (country/language/plan/segment)
- realistic consent mixes by purpose/channel
- event type/channel mixes and time-window spread

## 5. Indexing Strategy
Core indexes include:
1. multi-column profile filter index
2. GIN index on `profile_properties.custom_properties` using `jsonb_path_ops` for containment-heavy predicates (`@>`)
3. expression index on `custom_properties ->> 'plan'`
4. consent state and partial index for hot predicates
5. event time and campaign/profile time btree indexes
6. BRIN index on `message_events.event_time` for broad time-window scans
7. extended statistics (MCV) on common multi-column filters (`profiles`, `consent`, `message_events`)

Purpose:
- keep key lookups predictable
- support mixed JSONB + relational filters
- reduce planning/execution volatility on growth with improved selectivity inputs

## 6. Workload Catalog
### 6.1 Key reads (3)
1. profile lookup with JSONB properties
2. consent lookup for a profile/channel/purpose
3. segment candidate lookup with relational + consent filters

### 6.2 Key writes (2)
1. patch JSONB profile properties + increment version
2. consent upsert/update

Write-return contract note:
- `write_patch_properties` automated workflow depends on returned `new_version` to advance optimistic-lock state.
- Returned `old_*` fields may be observability-only placeholders in baseline catalogs and are not required for execution correctness.
- `write_upsert_consent` returned state fields are for inspection/report symmetry and are not consumed by run control flow.

### 6.3 Complex queries (3)
1. JSONB-heavy segmentation aggregation
2. 30-day campaign/channel event rollup
3. CTE + window + mixed joins across profile/properties/consent/events

## 7. Bloat and Maintenance Scenario
Intentional bloat workload:
1. repeated updates on `profile_properties` (primary target)
2. moderate state churn updates on `consent` (secondary)

Design note:
- no intentional bloat on `message_events` because it is modeled as append-heavy.

Expected use:
- run query suite before and after bloat workload
- compare latency and plan behavior

## 8. Execution Modes
Canonical run-script behavior reference:
- Run Modes (`RUN_MODES.md`)

### 8.1 Local mode (engineering)
Use Docker PostgreSQL for:
- schema/data/query correctness
- baseline artifact generation
- quick iteration on dataset/query/index changes
- configurable query profiles via `QUERY_RUN_PROFILE`:
  - `iterations` (deterministic latency percentiles)
  - `load` (concurrent throughput/QPS)
  - `both` (default)

### 8.2 DBA infra mode
Use DBA-provided environment for:
- deeper stress and longer runs
- infra-aware resource observations
- final performance interpretation
- the same query profiles and artifact schemas as local mode, driven by environment variables

### 8.3 Query Catalog Selection
Query files can be selected per run without changing script logic:
1. `SQL_CORE_FILE` (default: `sql/004_queries_core.sql`)
2. `SQL_COMPLEX_FILE` (default: `sql/005_queries_complex.sql`)

Selection rules:
1. If unset, defaults above are used.
2. Relative override values are resolved from project root.
3. Override paths must point to existing files or the run fails fast.
4. Baseline version catalogs remain unsuffixed (`004_queries_core.sql`, `005_queries_complex.sql`).

Use case:
1. Keep PostgreSQL `16.8` baseline catalogs unchanged.
2. Use overrides only for controlled experimental variants of the same workload shape.
3. Preserve workload intent and artifact compatibility across runs.

## 9. Output Artifacts and Handoff
Each run should produce:
1. timing artifacts under `results/<run_id>/`:
   - baseline mode: `timings.csv`, `timings_summary.csv`
   - bloat mode: `timings_pre_bloat.csv`, `timings_summary_pre_bloat.csv`, `timings_post_bloat.csv`, `timings_summary_post_bloat.csv`
2. load artifacts under `results/<run_id>/` when load mode is enabled:
   - baseline mode: `load_executions.csv`, `load_summary.csv`, `load_phase_summary.csv`
   - bloat mode: `load_executions_pre_bloat.csv`, `load_summary_pre_bloat.csv`, `load_phase_summary_pre_bloat.csv`, `load_executions_post_bloat.csv`, `load_summary_post_bloat.csv`, `load_phase_summary_post_bloat.csv`
3. optional `pg_stat_statements` artifacts (load mode):
   - baseline mode: `pg_stat_statements.csv`, `pg_stat_statements_status.txt`
   - bloat mode: `pg_stat_statements_pre_bloat.csv`, `pg_stat_statements_pre_bloat_status.txt`, `pg_stat_statements_post_bloat.csv`, `pg_stat_statements_post_bloat_status.txt`
4. `results/<run_id>/explain/*.txt` (captured for baseline/pre-bloat phase)
5. `results/<run_id>/summary.md`
6. run log line showing exact artifact directory path (`results/$RUN_ID/`)

Handoff expectation:
- artifacts are stable and reproducible from scripts
- explain plans are captured for complex queries
- summary includes key findings, notable regressions, and phase-level/per-query QPS in load mode

## 10. Open Decisions and DBA Inputs
Remaining external inputs:
1. explicit pass/fail thresholds for p95/p99 by query group
2. CPU/memory interpretation thresholds for risk/failure
3. any additional query scenarios DBA wants included

## 11. Next Extension Backlog
If more signal is needed after first runs:
1. add more JSONB predicate variants (`@>`, path + array conditions)
2. add tenant isolation stress patterns
3. add optional partitioning experiment for `message_events`
4. add read-replica-oriented query pack for OLAP-ish isolation testing
