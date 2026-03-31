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
export BLOAT_ROUNDS="${BLOAT_ROUNDS:-20}"
export RUN_ID="${RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
export QUERY_RUN_PROFILE="${QUERY_RUN_PROFILE:-both}"

run_sql_file() {
  local sql_file_rel="$1"
  uv run python -m poc.run_sql_file "$ROOT_DIR/$sql_file_rel"
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
