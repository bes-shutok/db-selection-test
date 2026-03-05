from __future__ import annotations

import csv
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from poc import run_queries


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, events: list[str]):
        self._events = events

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor()

    def commit(self):
        self._events.append("commit")

    def rollback(self):
        self._events.append("rollback")

    def close(self):
        self._events.append("close")


class _SqlStateError(Exception):
    def __init__(self, sqlstate: str, message: str = "connection dropped"):
        super().__init__(message)
        self.sqlstate = sqlstate


class RunQueriesTests(unittest.TestCase):
    def test_parse_named_queries_rejects_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "queries.sql"
            sql_path.write_text(
                "-- name: core_profile_lookup\nSELECT 1;\n"
                "-- name: core_profile_lookup\nSELECT 2;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Duplicate query name"):
                run_queries.parse_named_queries(sql_path)

    def test_merge_query_catalogs_rejects_overlap(self):
        with self.assertRaisesRegex(ValueError, "Duplicate query name"):
            run_queries.merge_query_catalogs(
                {"core_profile_lookup": "SELECT 1"},
                {"core_profile_lookup": "SELECT 2"},
            )

    def test_run_iterations_times_after_commit(self):
        events: list[str] = []
        perf_values = iter([10.0, 10.005])
        captured_rows: list[dict[str, object]] = []

        def fake_connect(_settings, autocommit=False):
            self.assertFalse(autocommit)
            return _FakeConnection(events)

        def fake_perf_counter():
            events.append("perf")
            return next(perf_values)

        def fake_write_iteration_outputs(_settings, _phase, rows, _by_query):
            captured_rows.extend(rows)

        settings = SimpleNamespace(query_iterations=1, results_dir=Path("."))
        queries = {"core_profile_lookup": "SELECT 1"}
        base_ctx = {"tenant_id": "t1", "profile_id": "p1"}

        with patch.object(run_queries, "connect", side_effect=fake_connect), patch.object(
            run_queries, "execute_query", return_value=(1, None)
        ), patch.object(
            run_queries, "write_iteration_outputs", side_effect=fake_write_iteration_outputs
        ), patch(
            "poc.run_queries.time.perf_counter", side_effect=fake_perf_counter
        ):
            run_queries.run_iterations(settings, queries, base_ctx, "baseline")

        self.assertEqual(events, ["perf", "commit", "perf"])
        self.assertEqual(len(captured_rows), 1)
        self.assertEqual(captured_rows[0]["query_name"], "core_profile_lookup")

    def test_load_worker_stops_after_reconnect_budget_exhausted(self):
        rows: list[dict[str, object]] = []
        rows_lock = threading.Lock()
        worker_errors: list[str] = []
        errors_lock = threading.Lock()
        connect_calls = {"count": 0}

        def fake_connect(_settings, autocommit=False):
            self.assertFalse(autocommit)
            connect_calls["count"] += 1
            return _FakeConnection([])

        monotonic_state = {"value": 0.0}
        perf_state = {"value": 1.0}

        def fake_monotonic():
            current = monotonic_state["value"]
            monotonic_state["value"] = current + 0.1
            return current

        def fake_perf_counter():
            current = perf_state["value"]
            perf_state["value"] = current + 0.001
            return current

        with patch.object(run_queries, "connect", side_effect=fake_connect), patch.object(
            run_queries,
            "execute_load_once",
            side_effect=_SqlStateError("08006"),
        ), patch(
            "poc.run_queries.time.monotonic", side_effect=fake_monotonic
        ), patch(
            "poc.run_queries.time.perf_counter", side_effect=fake_perf_counter
        ):
            run_queries.load_worker(
                worker_id=1,
                settings=SimpleNamespace(),
                phase="pre_bloat",
                queries={"core_profile_lookup": "SELECT 1"},
                weighted_names=["core_profile_lookup"],
                weighted_values=[1.0],
                seed_contexts=[{"tenant_id": "t1", "profile_id": "p1"}],
                warmup_until=0.0,
                stop_at=5.0,
                rows=rows,
                rows_lock=rows_lock,
                worker_errors=worker_errors,
                errors_lock=errors_lock,
            )

        self.assertEqual(connect_calls["count"], 2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["status"] == "error" for r in rows))
        self.assertEqual(worker_errors, [])

    def test_load_worker_error_elapsed_excludes_reconnect_wall_time(self):
        rows: list[dict[str, object]] = []
        rows_lock = threading.Lock()
        worker_errors: list[str] = []
        errors_lock = threading.Lock()
        events: list[str] = []

        def fake_connect(_settings, autocommit=False):
            self.assertFalse(autocommit)
            events.append("connect")
            return _FakeConnection([])

        monotonic_values = iter([0.0, 0.0, 1.0])
        perf_values = iter([10.0, 10.05])

        def fake_monotonic():
            return next(monotonic_values)

        def fake_perf_counter():
            events.append("perf")
            return next(perf_values)

        with patch.object(run_queries, "connect", side_effect=fake_connect), patch.object(
            run_queries,
            "execute_load_once",
            side_effect=_SqlStateError("08006"),
        ), patch(
            "poc.run_queries.time.monotonic", side_effect=fake_monotonic
        ), patch(
            "poc.run_queries.time.perf_counter", side_effect=fake_perf_counter
        ):
            run_queries.load_worker(
                worker_id=1,
                settings=SimpleNamespace(),
                phase="pre_bloat",
                queries={"core_profile_lookup": "SELECT 1"},
                weighted_names=["core_profile_lookup"],
                weighted_values=[1.0],
                seed_contexts=[{"tenant_id": "t1", "profile_id": "p1"}],
                warmup_until=0.0,
                stop_at=0.5,
                rows=rows,
                rows_lock=rows_lock,
                worker_errors=worker_errors,
                errors_lock=errors_lock,
            )

        self.assertEqual(events, ["connect", "perf", "perf", "connect"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["elapsed_ms"], 50.0)
        self.assertEqual(worker_errors, [])

    def test_write_load_outputs_uses_qps_window_and_writes_actual_elapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            settings = SimpleNamespace(
                results_dir=results_dir,
                load_workers=10,
                load_warmup_seconds=10,
            )
            queries = {"core_profile_lookup": "SELECT 1"}
            rows = [
                {
                    "phase": "pre_bloat",
                    "worker_id": 1,
                    "query_name": "core_profile_lookup",
                    "query_type": "read",
                    "started_at_utc": "2026-03-05T00:00:00+00:00",
                    "elapsed_ms": 10.0,
                    "rows": 1,
                    "status": "ok",
                    "error_code": "",
                    "error_message": "",
                }
                for _ in range(4)
            ]

            run_queries.write_load_outputs(
                settings,
                "pre_bloat",
                rows,
                queries,
                qps_window_seconds=10.0,
                actual_elapsed_seconds=14.0,
            )

            with (results_dir / "load_summary_pre_bloat.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                summary_rows = list(csv.DictReader(handle))
            self.assertEqual(summary_rows[0]["qps"], "0.4")

            with (results_dir / "load_phase_summary_pre_bloat.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                phase_rows = list(csv.DictReader(handle))
            self.assertEqual(phase_rows[0]["duration_seconds"], "10.0")
            self.assertEqual(phase_rows[0]["actual_elapsed_seconds"], "14.0")

    def test_run_load_uses_configured_duration_for_qps_window(self):
        captured: dict[str, float] = {}
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(
                results_dir=Path(tmp),
                load_capture_pg_stat_statements=False,
                load_warmup_seconds=10,
                load_duration_seconds=30,
                load_workers=0,
            )

            def fake_write_load_outputs(
                _settings,
                _phase,
                _rows,
                _queries,
                qps_window_seconds,
                actual_elapsed_seconds,
            ):
                captured["qps_window_seconds"] = qps_window_seconds
                captured["actual_elapsed_seconds"] = actual_elapsed_seconds

            with patch.object(
                run_queries,
                "resolve_load_weights",
                return_value={"core_profile_lookup": 1.0},
            ), patch.object(
                run_queries, "write_load_outputs", side_effect=fake_write_load_outputs
            ), patch(
                "poc.run_queries.time.monotonic", side_effect=[100.0, 160.0]
            ):
                run_queries.run_load(
                    settings,
                    "baseline",
                    {"core_profile_lookup": "SELECT 1"},
                    seed_contexts=[],
                )

        self.assertEqual(captured["qps_window_seconds"], 30.0)
        self.assertEqual(captured["actual_elapsed_seconds"], 50.0)


if __name__ == "__main__":
    unittest.main()
