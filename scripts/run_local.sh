#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-ups_poc}"
export DB_USER="${DB_USER:-ups_user}"
export DB_PASSWORD="${DB_PASSWORD:-ups_pass}"
export DB_SCHEMA="${DB_SCHEMA:-}"
export DB_SESSION_ROLE="${DB_SESSION_ROLE:-}"
export RUN_ID="${RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
export QUERY_RUN_PROFILE="${QUERY_RUN_PROFILE:-both}"

export PGPASSWORD="$DB_PASSWORD"

run_sql_file() {
  local sql_file_rel="$1"
  local sql_file_abs="$ROOT_DIR/$sql_file_rel"

  if command -v psql >/dev/null 2>&1; then
    {
      emit_session_bootstrap_sql
      cat "$sql_file_abs"
    } | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f -
    return
  fi

  if command -v docker >/dev/null 2>&1 && docker compose ps --services --status running | grep -q "^postgres$"; then
    {
      emit_session_bootstrap_sql
      cat "$sql_file_abs"
    } | docker compose exec -T -e PGPASSWORD="$DB_PASSWORD" postgres \
      psql -h localhost -p 5432 -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f -
    return
  fi

  echo "ERROR: psql is not installed and local postgres container is not running." >&2
  echo "Install psql, or run 'docker compose up -d' and retry." >&2
  exit 1
}

sql_ident() {
  local ident="$1"
  ident="${ident//\"/\"\"}"
  printf '"%s"' "$ident"
}

emit_session_bootstrap_sql() {
  local should_emit=0
  if [[ -n "${DB_SESSION_ROLE:-}" || -n "${DB_SCHEMA:-}" ]]; then
    should_emit=1
  fi

  if [[ "$should_emit" -eq 0 ]]; then
    return
  fi

  printf '\\set QUIET on\n'

  if [[ -n "${DB_SESSION_ROLE:-}" ]]; then
    printf 'SET ROLE %s;\n' "$(sql_ident "$DB_SESSION_ROLE")"
  fi

  if [[ -n "${DB_SCHEMA:-}" ]]; then
    printf 'SET search_path TO %s, public;\n' "$(sql_ident "$DB_SCHEMA")"
  fi

  printf '\\set QUIET off\n'
}

echo "Cleaning up previous run (dropping tables)..."
run_sql_file sql/000_cleanup.sql

echo "Applying schema and indexes..."
run_sql_file sql/001_schema.sql
run_sql_file sql/002_indexes.sql
echo "Generating synthetic data..."
uv run python -m poc.generate_data

echo "Loading data..."
uv run python -m poc.load_data

echo "Applying static reference seed..."
run_sql_file sql/003_seed_static.sql

echo "Running queries (pre-bloat)..."
uv run python -m poc.run_queries --phase pre_bloat --profile "$QUERY_RUN_PROFILE"

echo "Collecting bloat metrics (pre-bloat baseline)..."
run_sql_file sql/007_bloat_metrics.sql > "$ROOT_DIR/results/$RUN_ID/bloat_metrics_pre.txt"

echo "Applying intentional bloat workload..."
run_sql_file sql/006_bloat_workload.sql

echo "Collecting bloat metrics (post-bloat)..."
run_sql_file sql/007_bloat_metrics.sql > "$ROOT_DIR/results/$RUN_ID/bloat_metrics_post.txt"

echo "Running queries (post-bloat)..."
uv run python -m poc.run_queries --phase post_bloat --profile "$QUERY_RUN_PROFILE"

echo "Building summary report..."
uv run python -m poc.collect_report

echo "Run complete. Results are under $ROOT_DIR/results/$RUN_ID/"
echo ""
echo "Quick bloat comparison:"
if [[ "$QUERY_RUN_PROFILE" == "iterations" || "$QUERY_RUN_PROFILE" == "both" ]]; then
  echo "  diff results/$RUN_ID/timings_summary_pre_bloat.csv results/$RUN_ID/timings_summary_post_bloat.csv"
fi
if [[ "$QUERY_RUN_PROFILE" == "load" || "$QUERY_RUN_PROFILE" == "both" ]]; then
  echo "  diff results/$RUN_ID/load_phase_summary_pre_bloat.csv results/$RUN_ID/load_phase_summary_post_bloat.csv"
fi
