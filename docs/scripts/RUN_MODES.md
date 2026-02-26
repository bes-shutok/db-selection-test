# Core Concepts
- Local mode: validation flow executed from a developer machine, usually against local Docker PostgreSQL.
- DBA mode: same workload flow executed from a client machine against DBA-provided PostgreSQL infrastructure.
- Client-side `psql`: `psql` binary installed on the machine running the script, not on the remote DB server.

## 1. Purpose
This document is the canonical reference for `scripts/run_local.sh` and `scripts/run_on_dba_env.sh` behavior.

## 2. Shared Workflow
Both scripts run the same logical sequence:
1. cleanup (`sql/000_cleanup.sql`)
2. schema + indexes (`sql/001_schema.sql`, `sql/002_indexes.sql`)
3. data generation and load (`poc.generate_data`, `poc.load_data`)
4. static seed (`sql/003_seed_static.sql`)
5. pre-bloat query execution using `QUERY_RUN_PROFILE` (`iterations`, `load`, or `both`)
6. bloat workload (`sql/006_bloat_workload.sql`)
7. post-bloat query execution using `QUERY_RUN_PROFILE` (`iterations`, `load`, or `both`)
8. summary (`poc.collect_report`)

## 3. Key Differences
1. Environment variables
- `run_local.sh` provides defaults for DB connection values.
- `run_on_dba_env.sh` requires `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
- Both scripts default `QUERY_RUN_PROFILE=both` unless explicitly overridden.
- Both scripts support optional query catalog overrides:
  - `SQL_CORE_FILE` (default: `sql/004_queries_core.sql`)
  - `SQL_COMPLEX_FILE` (default: `sql/005_queries_complex.sql`)
  - Relative override values are resolved from project root.

2. SQL client behavior
- `run_local.sh` uses local `psql` when available, otherwise falls back to `docker compose exec ... psql` if local postgres container is running.
- `run_on_dba_env.sh` requires local `psql` and has no Docker fallback.

3. Where `psql` runs
- In DBA mode, `psql` runs on the machine invoking `./scripts/run_on_dba_env.sh`.
- It connects over the network to the server defined by `DB_HOST`/`DB_PORT`.
- No SSH hop is performed by the script.

## 4. Operational Guidance
1. Use local mode for correctness and fast iteration.
2. Use DBA mode for infrastructure-level validation and deeper performance interpretation.
3. Keep `.env` values explicit before DBA runs to avoid accidental local defaults.
4. Use `QUERY_RUN_PROFILE=both` for complete handoff artifacts (latency + QPS).
5. Treat unsuffixed SQL catalogs as baseline defaults for PostgreSQL `16.8`.
6. Use `SQL_CORE_FILE`/`SQL_COMPLEX_FILE` only for controlled experimental variants that preserve the same workload intent.

## 5. Artifact Examples
For run id `20260219_120000`, bloat mode with `QUERY_RUN_PROFILE=both` produces:
1. Iteration latency artifacts:
- `results/20260219_120000/timings_pre_bloat.csv`
- `results/20260219_120000/timings_summary_pre_bloat.csv`
- `results/20260219_120000/timings_post_bloat.csv`
- `results/20260219_120000/timings_summary_post_bloat.csv`
2. Load/QPS artifacts:
- `results/20260219_120000/load_executions_pre_bloat.csv`
- `results/20260219_120000/load_summary_pre_bloat.csv`
- `results/20260219_120000/load_phase_summary_pre_bloat.csv`
- `results/20260219_120000/load_executions_post_bloat.csv`
- `results/20260219_120000/load_summary_post_bloat.csv`
- `results/20260219_120000/load_phase_summary_post_bloat.csv`
3. Optional engine-side load diagnostics:
- `results/20260219_120000/pg_stat_statements_pre_bloat.csv`
- `results/20260219_120000/pg_stat_statements_post_bloat.csv`
- `results/20260219_120000/pg_stat_statements_pre_bloat_status.txt`
- `results/20260219_120000/pg_stat_statements_post_bloat_status.txt`
