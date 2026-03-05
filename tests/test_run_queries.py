from __future__ import annotations

import tempfile
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


if __name__ == "__main__":
    unittest.main()
