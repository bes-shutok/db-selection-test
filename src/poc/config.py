from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    data_scale: str
    profile_count: int
    event_count: int
    query_iterations: int
    bloat_rounds: int
    query_run_profile: str
    load_workers: int
    load_duration_seconds: int
    load_warmup_seconds: int
    load_seed_contexts: int
    load_query_mix: str
    load_query_weights_json: str | None
    load_capture_pg_stat_statements: bool
    load_pgstat_topn: int
    load_pgstat_policy: str
    run_id: str
    project_root: Path
    data_dir: Path
    results_dir: Path
    sql_core: Path
    sql_complex: Path


def _default_counts(scale: str) -> tuple[int, int]:
    if scale == "stretch":
        return 500_000, 20_000_000
    return 100_000, 5_000_000


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {raw_value}")


def _positive_int(env_name: str, default: str) -> int:
    value = int(os.getenv(env_name, default))
    if value <= 0:
        raise ValueError(f"{env_name} must be > 0")
    return value


def _non_negative_int(env_name: str, default: str) -> int:
    value = int(os.getenv(env_name, default))
    if value < 0:
        raise ValueError(f"{env_name} must be >= 0")
    return value


def _resolve_sql_path(root: Path, env_name: str, default_rel: str) -> Path:
    raw = (os.getenv(env_name) or "").strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
    else:
        candidate = root / default_rel

    resolved = candidate.resolve()
    if not resolved.exists():
        raise FileNotFoundError(
            f"{env_name} points to a missing SQL file: {resolved}"
        )
    if not resolved.is_file():
        raise ValueError(f"{env_name} must point to a file: {resolved}")
    return resolved


def load_settings() -> Settings:
    load_dotenv()

    scale = os.getenv("DATA_SCALE", "baseline").strip().lower()
    if scale not in {"baseline", "stretch"}:
        raise ValueError("DATA_SCALE must be baseline or stretch")

    query_run_profile = os.getenv("QUERY_RUN_PROFILE", "both").strip().lower()
    if query_run_profile not in {"iterations", "load", "both"}:
        raise ValueError("QUERY_RUN_PROFILE must be one of: iterations, load, both")

    load_query_mix = os.getenv("LOAD_QUERY_MIX", "balanced").strip().lower()
    if load_query_mix not in {"read_heavy", "balanced", "write_heavy", "custom"}:
        raise ValueError(
            "LOAD_QUERY_MIX must be one of: read_heavy, balanced, write_heavy, custom"
        )

    load_pgstat_policy = os.getenv("LOAD_PGSTAT_POLICY", "soft_fail").strip().lower()
    if load_pgstat_policy not in {"soft_fail", "hard_fail"}:
        raise ValueError("LOAD_PGSTAT_POLICY must be one of: soft_fail, hard_fail")

    default_profiles, default_events = _default_counts(scale)
    run_id = os.getenv("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    root = _project_root()
    data_dir = root / "data" / run_id
    results_dir = root / "results" / run_id
    sql_core = _resolve_sql_path(root, "SQL_CORE_FILE", "sql/004_queries_core.sql")
    sql_complex = _resolve_sql_path(
        root, "SQL_COMPLEX_FILE", "sql/005_queries_complex.sql"
    )

    return Settings(
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_name=os.getenv("DB_NAME", "ups_poc"),
        db_user=os.getenv("DB_USER", "ups_user"),
        db_password=os.getenv("DB_PASSWORD", "ups_pass"),
        data_scale=scale,
        profile_count=int(os.getenv("PROFILE_COUNT", str(default_profiles))),
        event_count=int(os.getenv("EVENT_COUNT", str(default_events))),
        # Default to 10 iterations: sufficient for cache warming and stable explain plans
        # without making local runs prohibitively slow. Increase for p99 benchmarks.
        query_iterations=_positive_int("QUERY_ITERATIONS", "10"),
        bloat_rounds=_positive_int("BLOAT_ROUNDS", "20"),
        query_run_profile=query_run_profile,
        load_workers=_positive_int("LOAD_WORKERS", "4"),
        load_duration_seconds=_positive_int("LOAD_DURATION_SECONDS", "120"),
        load_warmup_seconds=_non_negative_int("LOAD_WARMUP_SECONDS", "15"),
        load_seed_contexts=_positive_int("LOAD_SEED_CONTEXTS", "1000"),
        load_query_mix=load_query_mix,
        load_query_weights_json=os.getenv("LOAD_QUERY_WEIGHTS_JSON"),
        load_capture_pg_stat_statements=_parse_bool(
            os.getenv("LOAD_CAPTURE_PG_STAT_STATEMENTS"), True
        ),
        load_pgstat_topn=_positive_int("LOAD_PGSTAT_TOPN", "100"),
        load_pgstat_policy=load_pgstat_policy,
        run_id=run_id,
        project_root=root,
        data_dir=data_dir,
        results_dir=results_dir,
        sql_core=sql_core,
        sql_complex=sql_complex,
    )
