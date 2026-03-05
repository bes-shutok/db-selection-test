from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import LiteralString, cast

from psycopg import sql

from .config import Settings, load_settings
from .db import connect, ensure_dirs

LOAD_EXECUTION_FIELDS = [
    "phase",
    "worker_id",
    "query_name",
    "query_type",
    "started_at_utc",
    "elapsed_ms",
    "rows",
    "status",
    "error_code",
    "error_message",
]


def parse_named_queries(path: Path) -> dict[str, str]:
    queries: dict[str, list[str]] = {}
    current_name: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        if line.strip().startswith("-- name:"):
            current_name = line.split(":", 1)[1].strip()
            queries[current_name] = []
            continue

        if current_name:
            queries[current_name].append(line)

    return {
        name: "\n".join(lines).strip()
        for name, lines in queries.items()
        if "".join(lines).strip()
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    frac = idx - lower
    return ordered[lower] * (1 - frac) + ordered[upper] * frac


def query_kind(name: str) -> str:
    if name.startswith("write_"):
        return "write"
    if name.startswith("complex_"):
        return "complex"
    return "read"


def phase_suffix(phase: str) -> str:
    return f"_{phase}" if phase != "baseline" else ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return type(exc).__name__

    one_line = " | ".join(part.strip() for part in message.splitlines() if part.strip())
    if len(one_line) > 512:
        return one_line[:509] + "..."
    return one_line


def pick_seed_contexts(cur, limit: int) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT p.tenant_id,
               p.profile_id,
               pp.properties_version,
               COALESCE(p.country, 'NG') AS country,
               COALESCE(p.language, 'en') AS language
        FROM profiles p
        JOIN profile_properties pp
          ON pp.tenant_id = p.tenant_id
         AND pp.profile_id = p.profile_id
        WHERE p.status = 'ACTIVE'
        ORDER BY p.updated_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError("no ACTIVE profiles found")

    return [
        {
            "tenant_id": tenant_id,
            "profile_id": profile_id,
            "properties_version": int(properties_version),
            "country": country,
            "language": language,
        }
        for tenant_id, profile_id, properties_version, country, language in rows
    ]


def params_for_query(name: str, ctx: dict[str, object], iteration: int):
    if name == "core_profile_lookup":
        return (ctx["tenant_id"], ctx["profile_id"])
    if name == "core_consent_lookup":
        return (ctx["tenant_id"], ctx["profile_id"], "sms", "marketing")
    if name == "core_segment_candidates":
        return (
            ctx["tenant_id"],
            ctx["country"],
            ctx["language"],
            "sms",
            "marketing",
            "opted_in",
            500,
        )
    if name == "write_patch_properties":
        return (
            "pro" if iteration % 2 == 0 else "vip",
            ctx["tenant_id"],
            ctx["profile_id"],
            ctx["properties_version"],
        )
    if name == "write_upsert_consent":
        return (
            ctx["tenant_id"],
            ctx["profile_id"],
            "sms",
            "marketing",
            "opted_in" if iteration % 2 == 0 else "opted_out",
            "poc_runner",
        )
    if name in {
        "complex_jsonb_segmentation",
        "complex_event_rollup",
        "complex_join_filter",
    }:
        return (ctx["tenant_id"],)

    raise KeyError(f"no params mapping for query: {name}")


def execute_query(cur, query_str: str, params: tuple[object, ...]):
    cur.execute(sql.SQL(cast(LiteralString, query_str)), params)

    fetched_rows: list[tuple[object, ...]] | None = None
    if cur.description is not None:
        fetched_rows = cur.fetchall()
        result_rows = len(fetched_rows)
    else:
        result_rows = cur.rowcount

    return result_rows, fetched_rows


def refresh_properties_version(cur, tenant_id: str, profile_id: str) -> int | None:
    cur.execute(
        """
        SELECT properties_version
        FROM profile_properties
        WHERE tenant_id = %s AND profile_id = %s
        """,
        (tenant_id, profile_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return int(row[0])


def write_iteration_outputs(
    settings: Settings,
    phase: str,
    rows: list[dict[str, object]],
    by_query: dict[str, list[float]],
) -> None:
    suffix = phase_suffix(phase)
    timings_csv = settings.results_dir / f"timings{suffix}.csv"
    summary_csv = settings.results_dir / f"timings_summary{suffix}.csv"

    with timings_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["query_name", "query_type", "iteration", "elapsed_ms", "rows"],
        )
        writer.writeheader()
        writer.writerows(rows)

    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "query_name",
                "query_type",
                "p50_ms",
                "p95_ms",
                "p99_ms",
                "mean_ms",
                "runs",
            ]
        )
        for name, values in sorted(by_query.items()):
            writer.writerow(
                [
                    name,
                    query_kind(name),
                    round(percentile(values, 0.50), 3),
                    round(percentile(values, 0.95), 3),
                    round(percentile(values, 0.99), 3),
                    round(statistics.mean(values), 3),
                    len(values),
                ]
            )


def run_iterations(
    settings: Settings,
    queries: dict[str, str],
    base_ctx: dict[str, object],
    phase: str,
) -> None:
    rows: list[dict[str, object]] = []
    by_query: dict[str, list[float]] = defaultdict(list)
    ctx = dict(base_ctx)

    try:
        with connect(settings, autocommit=False) as conn:
            with conn.cursor() as cur:
                for name, query_str in queries.items():
                    for i in range(1, settings.query_iterations + 1):
                        params = params_for_query(name, ctx, i)
                        started = time.perf_counter()
                        result_rows, fetched_rows = execute_query(cur, query_str, params)

                        elapsed_ms = (time.perf_counter() - started) * 1000
                        by_query[name].append(elapsed_ms)
                        rows.append(
                            {
                                "query_name": name,
                                "query_type": query_kind(name),
                                "iteration": i,
                                "elapsed_ms": round(elapsed_ms, 3),
                                "rows": result_rows,
                            }
                        )

                        if (
                            name == "write_patch_properties"
                            and fetched_rows
                            and len(fetched_rows[0]) >= 2
                        ):
                            ctx["properties_version"] = int(fetched_rows[0][1])

                        conn.commit()
    finally:
        write_iteration_outputs(settings, phase, rows, by_query)


def resolve_load_weights(settings: Settings, queries: dict[str, str]) -> dict[str, float]:
    query_names = list(queries.keys())

    if settings.load_query_mix == "custom":
        raw = settings.load_query_weights_json
        if not raw:
            raise ValueError(
                "LOAD_QUERY_WEIGHTS_JSON is required when LOAD_QUERY_MIX=custom"
            )

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LOAD_QUERY_WEIGHTS_JSON must be a JSON object")

        weights: dict[str, float] = {}
        for key, value in parsed.items():
            if key not in queries:
                raise ValueError(f"unknown query in LOAD_QUERY_WEIGHTS_JSON: {key}")
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"weight for query '{key}' must be numeric, got: {type(value).__name__}"
                )
            if value < 0:
                raise ValueError(f"weight for query '{key}' must be >= 0")
            weights[key] = float(value)

        full_weights = {name: weights.get(name, 0.0) for name in query_names}
        if sum(full_weights.values()) <= 0:
            raise ValueError("LOAD_QUERY_WEIGHTS_JSON must define at least one positive weight")
        return full_weights

    mix_type_weights = {
        "read_heavy": {"read": 0.70, "write": 0.20, "complex": 0.10},
        "balanced": {"read": 0.45, "write": 0.35, "complex": 0.20},
        "write_heavy": {"read": 0.25, "write": 0.60, "complex": 0.15},
    }

    type_weights = mix_type_weights[settings.load_query_mix]
    by_type: dict[str, list[str]] = {"read": [], "write": [], "complex": []}
    for name in query_names:
        by_type[query_kind(name)].append(name)

    weights: dict[str, float] = {name: 0.0 for name in query_names}
    for query_type, total_weight in type_weights.items():
        names = by_type[query_type]
        if not names:
            continue
        per_query_weight = total_weight / len(names)
        for name in names:
            weights[name] = per_query_weight

    if sum(weights.values()) <= 0:
        raise ValueError("load query weights resolved to zero")
    return weights


def is_pg_stat_extension_available(cur) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements')"
    )
    row = cur.fetchone()
    return bool(row and row[0])


def apply_pgstat_policy(settings: Settings, message: str) -> None:
    if settings.load_pgstat_policy == "hard_fail":
        raise RuntimeError(message)
    print(f"WARN: {message}")


def reset_pg_stat_statements(settings: Settings, phase: str) -> tuple[bool, str]:
    try:
        with connect(settings, autocommit=True) as conn:
            with conn.cursor() as cur:
                if not is_pg_stat_extension_available(cur):
                    return False, f"{phase}: pg_stat_statements extension is not installed"
                cur.execute("SELECT pg_stat_statements_reset()")
                return True, f"{phase}: pg_stat_statements_reset executed"
    except Exception as exc:  # pragma: no cover - depends on runtime DB setup
        return False, f"{phase}: pg_stat_statements reset failed: {exc}"


def capture_pg_stat_statements(settings: Settings, phase: str) -> tuple[bool, str]:
    suffix = phase_suffix(phase)
    out_path = settings.results_dir / f"pg_stat_statements{suffix}.csv"

    try:
        with connect(settings, autocommit=True) as conn:
            with conn.cursor() as cur:
                if not is_pg_stat_extension_available(cur):
                    return False, f"{phase}: pg_stat_statements extension is not installed"

                cur.execute("SELECT * FROM pg_stat_statements LIMIT 0")
                available_columns = [column.name for column in cur.description or []]
                if not available_columns:
                    return False, f"{phase}: pg_stat_statements has no visible columns"

                ordered_candidates = [
                    "queryid",
                    "calls",
                    "total_exec_time",
                    "total_time",
                    "mean_exec_time",
                    "mean_time",
                    "total_plan_time",
                    "mean_plan_time",
                    "plans",
                    "rows",
                    "shared_blks_hit",
                    "shared_blks_read",
                    "local_blks_hit",
                    "local_blks_read",
                    "temp_blks_read",
                    "temp_blks_written",
                    "wal_records",
                    "wal_fpi",
                    "wal_bytes",
                    "jit_functions",
                    "jit_generation_time",
                    "jit_inlining_count",
                    "jit_inlining_time",
                    "jit_optimization_count",
                    "jit_optimization_time",
                    "jit_emission_count",
                    "jit_emission_time",
                    "query",
                ]
                selected_columns = [
                    name for name in ordered_candidates if name in available_columns
                ]
                if "query" not in selected_columns:
                    return False, f"{phase}: pg_stat_statements.query column is unavailable"

                if "total_exec_time" in selected_columns:
                    order_column = "total_exec_time"
                elif "total_time" in selected_columns:
                    order_column = "total_time"
                else:
                    return False, (
                        f"{phase}: pg_stat_statements lacks total execution time column "
                        "(expected total_exec_time or total_time)"
                    )

                stmt = sql.SQL(
                    "SELECT {columns} FROM pg_stat_statements "
                    "ORDER BY {order_column} DESC LIMIT %s"
                ).format(
                    columns=sql.SQL(", ").join(sql.Identifier(name) for name in selected_columns),
                    order_column=sql.Identifier(order_column),
                )
                cur.execute(stmt, (settings.load_pgstat_topn,))
                rows = cur.fetchall()

        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(selected_columns)
            writer.writerows(rows)

        return True, (
            f"{phase}: captured pg_stat_statements top {len(rows)} rows to {out_path.name}"
        )
    except Exception as exc:  # pragma: no cover - depends on runtime DB setup
        return False, f"{phase}: failed to capture pg_stat_statements: {exc}"


def write_pgstat_status(settings: Settings, phase: str, message: str) -> None:
    suffix = phase_suffix(phase)
    status_path = settings.results_dir / f"pg_stat_statements{suffix}_status.txt"
    status_path.write_text(message + "\n", encoding="utf-8")


def execute_load_once(
    *,
    cur,
    query_name: str,
    query_str: str,
    ctx: dict[str, object],
    iteration: int,
    local_versions: dict[tuple[str, str], int],
) -> tuple[int, str, str]:
    tenant_id = str(ctx["tenant_id"])
    profile_id = str(ctx["profile_id"])
    entity_key = (tenant_id, profile_id)

    if query_name == "write_patch_properties" and entity_key in local_versions:
        ctx["properties_version"] = local_versions[entity_key]

    params = params_for_query(query_name, ctx, iteration)
    result_rows, fetched_rows = execute_query(cur, query_str, params)

    if query_name == "write_patch_properties":
        if fetched_rows and len(fetched_rows[0]) >= 2:
            local_versions[entity_key] = int(fetched_rows[0][1])
            return result_rows, "ok", ""

        if result_rows == 0:
            refreshed = refresh_properties_version(cur, tenant_id, profile_id)
            if refreshed is None:
                return 0, "conflict", ""

            local_versions[entity_key] = refreshed
            ctx["properties_version"] = refreshed
            retry_params = params_for_query(query_name, ctx, iteration + 1)
            retry_rows, retry_fetched = execute_query(cur, query_str, retry_params)
            if retry_fetched and len(retry_fetched[0]) >= 2:
                local_versions[entity_key] = int(retry_fetched[0][1])
                return retry_rows, "ok_retry", ""
            if retry_rows == 0:
                return 0, "conflict", ""
            return retry_rows, "ok_retry", ""

    return result_rows, "ok", ""


def load_worker(
    *,
    worker_id: int,
    settings: Settings,
    phase: str,
    queries: dict[str, str],
    weighted_names: list[str],
    weighted_values: list[float],
    seed_contexts: list[dict[str, object]],
    warmup_until: float,
    stop_at: float,
    rows: list[dict[str, object]],
    rows_lock: threading.Lock,
    worker_errors: list[str],
    errors_lock: threading.Lock,
) -> None:
    try:
        rng = random.Random(100_000 + worker_id)
        local_versions: dict[tuple[str, str], int] = {}
        iteration = 0

        conn = connect(settings, autocommit=False)
        reconnect_attempts_left = 1
        try:
            cur = conn.cursor()
            while time.monotonic() < stop_at:
                now = time.monotonic()
                record_row = now >= warmup_until

                iteration += 1
                query_name = rng.choices(weighted_names, weights=weighted_values, k=1)[0]
                query_str = queries[query_name]
                ctx = dict(rng.choice(seed_contexts))

                started_at = utc_now_iso()
                started = time.perf_counter()
                result_rows = 0
                status = "ok"
                error_code = ""
                error_message = ""

                try:
                    result_rows, status, error_code = execute_load_once(
                        cur=cur,
                        query_name=query_name,
                        query_str=query_str,
                        ctx=ctx,
                        iteration=iteration,
                        local_versions=local_versions,
                    )
                    if status == "conflict":
                        # Conflict is a handled write miss (optimistic version mismatch),
                        # not a thrown DB exception, so populate explicit signature fields.
                        error_code = "conflict"
                        error_message = (
                            "write_patch_properties optimistic lock conflict "
                            "(0 rows affected after retry)"
                        )
                    conn.commit()
                except Exception as exc:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    status = "error"
                    error_code = getattr(exc, "sqlstate", "") or type(exc).__name__
                    error_message = format_exception_message(exc)

                    sqlstate = getattr(exc, "sqlstate", "") or ""
                    if sqlstate.startswith("08") and reconnect_attempts_left > 0:
                        reconnect_attempts_left -= 1
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = connect(settings, autocommit=False)
                        cur = conn.cursor()

                elapsed_ms = (time.perf_counter() - started) * 1000
                if record_row:
                    row = {
                        "phase": phase,
                        "worker_id": worker_id,
                        "query_name": query_name,
                        "query_type": query_kind(query_name),
                        "started_at_utc": started_at,
                        "elapsed_ms": round(elapsed_ms, 3),
                        "rows": result_rows,
                        "status": status,
                        "error_code": error_code,
                        "error_message": error_message,
                    }
                    with rows_lock:
                        rows.append(row)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as exc:
        with errors_lock:
            worker_errors.append(f"worker {worker_id} failed: {exc}")


def write_load_outputs(
    settings: Settings,
    phase: str,
    rows: list[dict[str, object]],
    queries: dict[str, str],
    phase_elapsed_seconds: float,
) -> None:
    suffix = phase_suffix(phase)
    executions_path = settings.results_dir / f"load_executions{suffix}.csv"
    summary_path = settings.results_dir / f"load_summary{suffix}.csv"
    phase_summary_path = settings.results_dir / f"load_phase_summary{suffix}.csv"

    with executions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOAD_EXECUTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    latency_by_query: dict[str, list[float]] = defaultdict(list)
    calls_by_query: dict[str, int] = defaultdict(int)
    errors_by_query: dict[str, int] = defaultdict(int)

    for row in rows:
        query_name = str(row["query_name"])
        calls_by_query[query_name] += 1
        if row["status"] in {"ok", "ok_retry"}:
            latency_by_query[query_name].append(float(row["elapsed_ms"]))
        else:
            errors_by_query[query_name] += 1

    duration = max(phase_elapsed_seconds, 0.001)

    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "query_name",
                "query_type",
                "calls",
                "errors",
                "p50_ms",
                "p95_ms",
                "p99_ms",
                "mean_ms",
                "qps",
            ]
        )

        for query_name in sorted(queries.keys()):
            values = latency_by_query.get(query_name, [])
            calls = calls_by_query.get(query_name, 0)
            errors = errors_by_query.get(query_name, 0)
            if values:
                p50 = round(percentile(values, 0.50), 3)
                p95 = round(percentile(values, 0.95), 3)
                p99 = round(percentile(values, 0.99), 3)
                mean = round(statistics.mean(values), 3)
            else:
                p50 = 0.0
                p95 = 0.0
                p99 = 0.0
                mean = 0.0

            writer.writerow(
                [
                    query_name,
                    query_kind(query_name),
                    calls,
                    errors,
                    p50,
                    p95,
                    p99,
                    mean,
                    round(calls / duration, 3),
                ]
            )

    total_errors = sum(errors_by_query.values())
    total_calls = len(rows)
    with phase_summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "phase",
                "workers",
                "warmup_seconds",
                "duration_seconds",
                "total_calls",
                "total_errors",
                "overall_qps",
            ]
        )
        writer.writerow(
            [
                phase,
                settings.load_workers,
                settings.load_warmup_seconds,
                round(duration, 3),
                total_calls,
                total_errors,
                round(total_calls / duration, 3),
            ]
        )


def run_load(
    settings: Settings,
    phase: str,
    queries: dict[str, str],
    seed_contexts: list[dict[str, object]],
) -> None:
    weights = resolve_load_weights(settings, queries)
    weighted_names = [name for name in queries.keys() if weights[name] > 0]
    weighted_values = [weights[name] for name in weighted_names]

    pgstat_messages: list[str] = []
    if settings.load_capture_pg_stat_statements:
        reset_ok, reset_msg = reset_pg_stat_statements(settings, phase)
        pgstat_messages.append(reset_msg)
        if not reset_ok:
            write_pgstat_status(settings, phase, "\n".join(pgstat_messages))
            apply_pgstat_policy(settings, reset_msg)
    else:
        pgstat_messages.append(f"{phase}: pg_stat_statements capture disabled by config")

    rows: list[dict[str, object]] = []
    rows_lock = threading.Lock()
    worker_errors: list[str] = []
    errors_lock = threading.Lock()

    warmup_until = time.monotonic() + settings.load_warmup_seconds
    stop_at = warmup_until + settings.load_duration_seconds

    workers = [
        threading.Thread(
            target=load_worker,
            kwargs={
                "worker_id": worker_id,
                "settings": settings,
                "phase": phase,
                "queries": queries,
                "weighted_names": weighted_names,
                "weighted_values": weighted_values,
                "seed_contexts": seed_contexts,
                "warmup_until": warmup_until,
                "stop_at": stop_at,
                "rows": rows,
                "rows_lock": rows_lock,
                "worker_errors": worker_errors,
                "errors_lock": errors_lock,
            },
            daemon=False,
        )
        for worker_id in range(1, settings.load_workers + 1)
    ]

    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    if worker_errors:
        raise RuntimeError("; ".join(worker_errors))

    phase_elapsed_seconds = max(0.001, time.monotonic() - warmup_until)
    write_load_outputs(settings, phase, rows, queries, phase_elapsed_seconds)

    if settings.load_capture_pg_stat_statements:
        capture_ok, capture_msg = capture_pg_stat_statements(settings, phase)
        pgstat_messages.append(capture_msg)
        if not capture_ok:
            write_pgstat_status(settings, phase, "\n".join(pgstat_messages))
            apply_pgstat_policy(settings, capture_msg)

    write_pgstat_status(settings, phase, "\n".join(pgstat_messages))


def generate_explain(
    settings: Settings,
    phase: str,
    complex_queries: dict[str, str],
    seed_ctx: dict[str, object],
) -> None:
    if phase not in {"pre_bloat", "baseline"}:
        return

    with connect(settings, autocommit=False) as conn:
        with conn.cursor() as cur:
            for name, query_str in complex_queries.items():
                params = params_for_query(name, seed_ctx, 1)
                cur.execute(
                    sql.SQL("EXPLAIN (ANALYZE, BUFFERS) {}").format(
                        sql.SQL(cast(LiteralString, query_str))
                    ),
                    params,
                )
                explain_text = "\n".join(line for (line,) in cur.fetchall())
                (settings.results_dir / "explain" / f"{name}.txt").write_text(
                    explain_text, encoding="utf-8"
                )


def selected_modes(profile: str) -> list[str]:
    if profile == "both":
        return ["iterations", "load"]
    return [profile]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run CRM POC queries and collect timing/load metrics"
    )
    parser.add_argument(
        "--phase",
        default="baseline",
        choices=["baseline", "pre_bloat", "post_bloat"],
        help="Testing phase label for output files (default: baseline)",
    )
    parser.add_argument(
        "--profile",
        choices=["iterations", "load", "both"],
        default=None,
        help="Run profile override (default: QUERY_RUN_PROFILE env)",
    )
    args = parser.parse_args()

    settings = load_settings()
    ensure_dirs(settings.results_dir, settings.results_dir / "explain")

    profile = (args.profile or settings.query_run_profile).strip().lower()
    modes = selected_modes(profile)

    core_queries = parse_named_queries(settings.sql_core)
    complex_queries = parse_named_queries(settings.sql_complex)
    all_queries = {**core_queries, **complex_queries}

    seed_limit = settings.load_seed_contexts if "load" in modes else 1
    with connect(settings, autocommit=False) as conn:
        with conn.cursor() as cur:
            seed_contexts = pick_seed_contexts(cur, seed_limit)

    if "iterations" in modes:
        run_iterations(settings, all_queries, seed_contexts[0], args.phase)

    if "load" in modes:
        run_load(settings, args.phase, all_queries, seed_contexts)

    generate_explain(settings, args.phase, complex_queries, seed_contexts[0])

    print(
        f"query run complete: {settings.results_dir} "
        f"(phase={args.phase}, modes={','.join(modes)})"
    )


if __name__ == "__main__":
    main()
