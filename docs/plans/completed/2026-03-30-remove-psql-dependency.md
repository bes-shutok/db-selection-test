# Plan: Remove psql Dependency From Run Scripts

## Context
The DBA run flow currently fails on locked-down Linux hosts because `scripts/run_on_dba_env.sh` hard-requires a local `psql` binary even though the measured workload, loading, and reporting paths already run through Python. We want a behavior-preserving replacement that executes the SQL catalogs through the existing `psycopg` stack without materially changing setup, bloat generation, or artifact contents. The highest-risk constraint is preserving `psql` semantics for session bootstrap, `:BLOAT_ROUNDS` substitution, and utility statements such as `VACUUM (ANALYZE)` in `sql/006_bloat_workload.sql`, so the change should be delivered with narrow RED → GREEN → REFACTOR steps and targeted verification after each increment.

## Validation Commands
```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src uv run python -m unittest tests.test_sql_runner
PYTHONPATH=src uv run python -m poc.run_sql_file --help
```

### Task 1: Add TDD coverage for SQL file execution semantics
Files:
- `tests/test_sql_runner.py` *(new)*
- `src/poc/sql_runner.py` *(new)*
- `sql/006_bloat_workload.sql`

- [x] Write failing test: `SqlRunnerTests#test_substitutes_bloat_rounds_placeholder_before_execution`
- [x] Run → expect RED: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Write minimal implementation in `src/poc/sql_runner.py` to load SQL text and substitute `:BLOAT_ROUNDS`
- [x] Run → expect GREEN: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Write failing test: `SqlRunnerTests#test_applies_session_role_and_search_path_before_sql_execution`
- [x] Run → expect RED: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Write minimal implementation in `src/poc/sql_runner.py` to connect through `poc.db.connect()` and preserve session bootstrap behavior
- [x] Run → expect GREEN: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Write failing test: `SqlRunnerTests#test_executes_vacuum_statements_outside_transaction`
- [x] Run → expect RED: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Write minimal implementation in `src/poc/sql_runner.py` to split utility statements and execute them with autocommit
- [x] Run → expect GREEN: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Refactor parser/executor helpers in `src/poc/sql_runner.py` only after tests pass

### Task 2: Switch run scripts to the Python SQL runner without changing workload order
Files:
- `scripts/run_on_dba_env.sh`
- `scripts/run_local.sh`
- `src/poc/sql_runner.py`

- [x] Write failing test: `SqlRunnerTests#test_cli_runs_sql_file_and_returns_non_zero_on_execution_error`
- [x] Run → expect RED: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Add a small CLI entry point in `src/poc/sql_runner.py` that accepts a SQL file path and required variables
- [x] Update `scripts/run_on_dba_env.sh` to call the Python runner instead of hard-failing on missing `psql`
- [x] Update `scripts/run_local.sh` to use the same Python runner path so local and DBA execution stay behavior-aligned
- [x] Run → expect GREEN: `PYTHONPATH=src uv run python -m unittest tests.test_sql_runner`
- [x] Run regression suite: `PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py'`
- [x] Refactor shared shell command assembly only if both scripts still preserve the same step ordering and artifact paths

### Task 3: Document the new SQL execution path and operator guidance
Files:
- `README.md`
- `docs/scripts/RUN_MODES.md`
- `docs/CRM_POC_SPEC.md`

- [x] Update `README.md` to remove `psql` as a hard DBA prerequisite and explain when a local PostgreSQL client is still optional vs unnecessary
- [x] Update `docs/scripts/RUN_MODES.md` to describe the Python SQL runner as the canonical execution path for SQL catalogs, including preserved session bootstrap behavior
- [x] Update `docs/CRM_POC_SPEC.md` only where it references run-mode prerequisites or execution behavior so the spec stays aligned with the scripts
- [x] Run verification read-through on the changed docs to confirm they still use the same run sequence and artifact naming as the scripts
