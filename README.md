# CRM PostgreSQL POC

## Core Concepts
- POC: focused validation project for PostgreSQL behavior on CRM-like workloads.
- Lean scope: only the tables and queries needed to test JSONB-heavy and OLAP-ish patterns.
- Baseline vs stretch: two data scales to observe plan/latency behavior under growth.
- Bloat phase: intentional update-heavy workload on selected tables to test MVCC side effects.

## Scope
This project validates a lean CRM data shape:
- `profiles`
- `profile_properties` (JSONB-heavy)
- `consent`
- `message_events`

Workload set:
- 3 key reads
- 2 key writes
- 3 complex queries (JSONB segmentation, aggregation, mixed join/filter)

## Document Positioning
- This repository is the implementation source of truth (schema, workload, scripts, artifacts).
- Stakeholder-facing scope/assumptions snapshots may be maintained separately in the documentation workspace before full spec rollout.
- If assumptions and implementation diverge, update both with an explicit reconciliation note in the same change.

## Documentation
- Project operating guide: `AGENTS.md`
- Full CRM context and POC spec: `docs/CRM_POC_SPEC.md`
- Run mode behavior and SQL execution path: `docs/scripts/RUN_MODES.md`
- Decision rationale log: `docs/DECISION_RATIONALE.md`
- Stakeholder communication log: `docs/COMMUNICATION_LOG.md`
- PostgreSQL baseline optimization notes: `docs/POSTGRES_BASELINE_OPTIMIZATIONS.md`

## Prerequisites
- Python `3.14.2`
- `uv` `0.10.0`
- Docker (required only for local PostgreSQL)

No `psql` binary is required. SQL catalog files are executed through the Python SQL runner (`poc.run_sql_file`), which connects via `psycopg`. A local PostgreSQL client is optional and only useful for ad-hoc manual queries outside the run scripts.

If `uv` is not installed for your current user yet on Linux or macOS, install the pinned version with:
```bash
python3 -m pip install --user pipx
python3 -m pipx install uv==0.10.0
```

Choose your setup mode:
- **Local mode**: Uses Docker to run PostgreSQL locally
- **Remote mode**: Connects to an external database server (e.g., RDS, Cloud SQL, or any managed PostgreSQL)

## Pinned Versions
- PostgreSQL image: `postgres:16.8`
- Python runtime: `3.14.2` (`.python-version`)
- `psycopg[binary]`: `3.3.2`
- `faker`: `40.4.0`
- `numpy`: `2.4.2`
- `python-dotenv`: `1.2.1`
- `rich`: `14.3.2`
- build backend (`hatchling`): `1.28.0`

## Quick Start

### Option 1: Local Mode (Docker PostgreSQL)

1. Copy env file:
```bash
cp .env.example .env
```

2. Install dependencies:
```bash
uv sync
```

3. Start PostgreSQL in Docker:
```bash
docker compose up -d
```

4. Run the full local workflow:
```bash
./scripts/run_local.sh
```

### Option 2: Remote Mode (External DB Server)

For running tests against a remote PostgreSQL instance (e.g., Amazon RDS, Google Cloud SQL, Azure Database, or any self-managed server):

1. Copy and configure the env file with your remote database connection:
```bash
cp .env.example .env
```

2. Edit `.env` with your remote database credentials:
```bash
# Remote database connection
DB_HOST=your-db-host.region.rds.amazonaws.com  # or your DB endpoint
DB_PORT=5432                                     # default PostgreSQL port
DB_NAME=your_db_name                             # database name
DB_USER=your_db_user                             # database user
DB_PASSWORD=your_password                        # database password

# Optional: Use a specific schema (for multi-tenant setups)
DB_SCHEMA=your_schema_name

# Optional: Run as a specific role (requires SET ROLE privilege)
DB_SESSION_ROLE=your_role_name
```

3. Install dependencies:
```bash
uv sync
```

4. Run against the remote database:
```bash
./scripts/run_on_dba_env.sh
```

**Important notes for remote mode:**
- No Docker is required—the script connects directly to your remote database
- Ensure your network allows outbound connections to the database host/port
- The database user must have privileges to create tables, indexes, and schemas
- For RDS/AWS: ensure security groups allow connections from your IP
- For Cloud SQL: ensure connections are authorized (IAM or password-based)

## Query Run Profiles
- `QUERY_RUN_PROFILE=iterations`: deterministic single-connection latency sampling (`timings*.csv`).
- `QUERY_RUN_PROFILE=load`: concurrent worker load mode with throughput/QPS outputs (`load_*.csv`).
- `QUERY_RUN_PROFILE=both` (default): run both modes in each phase.

## Query Catalog Selection
- `SQL_CORE_FILE`: optional override for core query catalog path.
- `SQL_COMPLEX_FILE`: optional override for complex query catalog path.
- If unset, defaults are:
  - `sql/004_queries_core.sql`
  - `sql/005_queries_complex.sql`
- Relative override values are resolved from the project root.

Common load controls:
- `LOAD_WORKERS`
- `LOAD_DURATION_SECONDS`
- `LOAD_WARMUP_SECONDS`
- `LOAD_QUERY_MIX` (`read_heavy`, `balanced`, `write_heavy`, `custom`)
- `LOAD_QUERY_WEIGHTS_JSON` (required for `LOAD_QUERY_MIX=custom`)
- `LOAD_CAPTURE_PG_STAT_STATEMENTS`, `LOAD_PGSTAT_TOPN`, `LOAD_PGSTAT_POLICY`

Optional local Docker PostgreSQL controls:
- `PG_MAX_CONNECTIONS`
- `PG_SHARED_BUFFERS`
- `PG_WORK_MEM`
- `PG_MAX_PARALLEL_WORKERS_PER_GATHER`
- `PG_SHM_SIZE`
- `PG_JIT`

## Output Artifacts
Each run writes to `results/<run_id>/`:
- Iteration timing artifacts:
  - `timings_pre_bloat.csv`, `timings_summary_pre_bloat.csv`
  - `timings_post_bloat.csv`, `timings_summary_post_bloat.csv`
- Load artifacts (when load mode is enabled):
  - `load_executions_pre_bloat.csv`, `load_summary_pre_bloat.csv`, `load_phase_summary_pre_bloat.csv`
  - `load_executions_post_bloat.csv`, `load_summary_post_bloat.csv`, `load_phase_summary_post_bloat.csv`
- Optional load engine-side stats:
  - `pg_stat_statements_pre_bloat.csv`, `pg_stat_statements_post_bloat.csv`
  - `pg_stat_statements_pre_bloat_status.txt`, `pg_stat_statements_post_bloat_status.txt`
- `summary.md`
- `explain/*.txt`
- `data/<run_id>/metadata.json`
- Run scripts print the concrete results path at completion (`results/$RUN_ID/`).

## Notes
- Baseline defaults: `100k profiles + 5M events`
- Stretch defaults: `500k profiles + 20M events`
- Consent behavior/performance validation baseline: PostgreSQL `16.8`
- Success thresholds (p95/p99/CPU/memory) are provided by DBA.
