from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from poc import sql_runner


class SqlRunnerTests(unittest.TestCase):
    def test_substitutes_bloat_rounds_placeholder_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "bloat.sql"
            sql_path.write_text(
                "FOR i IN 1..:BLOAT_ROUNDS LOOP\n  SELECT 1;\nEND LOOP;\n",
                encoding="utf-8",
            )

            result = sql_runner.load_and_substitute(sql_path, {"BLOAT_ROUNDS": "5"})

            self.assertIn("1..5 LOOP", result)
            self.assertNotIn(":BLOAT_ROUNDS", result)

    def test_substitutes_psql_single_quoted_variable_as_sql_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "bloat_literal.sql"
            sql_path.write_text(
                "SELECT set_config('poc.bloat_rounds', :'BLOAT_ROUNDS', false);\n",
                encoding="utf-8",
            )

            result = sql_runner.load_and_substitute(sql_path, {"BLOAT_ROUNDS": "5"})

            self.assertIn("set_config('poc.bloat_rounds', '5', false)", result)
            self.assertNotIn(":'BLOAT_ROUNDS'", result)

    def test_connect_receives_settings_with_session_fields(self):
        captured_settings: list[object] = []

        def fake_connect(settings, autocommit=False):
            captured_settings.append(settings)
            conn = MagicMock()
            conn.autocommit = False
            cursor = MagicMock()
            cursor.__enter__ = lambda s: s
            cursor.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cursor
            conn.commit = MagicMock()
            conn.close = MagicMock()
            return conn

        settings = SimpleNamespace(
            db_session_role="test_role",
            db_schema="test_schema",
        )

        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "simple.sql"
            sql_path.write_text("SELECT 1;\n", encoding="utf-8")

            with patch.object(sql_runner, "connect", side_effect=fake_connect):
                sql_runner.run_sql_file(sql_path, settings, {})

        self.assertEqual(len(captured_settings), 1)
        used = captured_settings[0]
        self.assertEqual(used.db_session_role, "test_role")
        self.assertEqual(used.db_schema, "test_schema")

    def test_executes_vacuum_statements_outside_transaction(self):
        autocommit_values: list[bool] = []
        executed: list[str] = []

        def fake_connect(_settings, autocommit=False):
            conn = MagicMock()

            type(conn).autocommit = property(
                lambda self: getattr(self, "_autocommit", False),
                lambda self, val: (
                    autocommit_values.append(val),
                    setattr(self, "_autocommit", val),
                ),
            )

            cursor = MagicMock()
            cursor.__enter__ = lambda s: s
            cursor.__exit__ = MagicMock(return_value=False)
            cursor.execute.side_effect = lambda sql: executed.append(sql)
            conn.cursor.return_value = cursor
            conn.commit = MagicMock()
            conn.close = MagicMock()
            return conn

        settings = SimpleNamespace(db_session_role=None, db_schema=None)

        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "vacuum.sql"
            sql_path.write_text(
                "DO $$ BEGIN NULL; END $$;\nVACUUM (ANALYZE) profile_properties;\n",
                encoding="utf-8",
            )

            with patch.object(sql_runner, "connect", side_effect=fake_connect):
                sql_runner.run_sql_file(sql_path, settings, {})

        self.assertEqual(
            autocommit_values,
            [True, False],
            "expected autocommit toggled True for VACUUM then back to False",
        )
        self.assertEqual(len(executed), 2)
        self.assertTrue(executed[0].startswith("DO $$"))
        self.assertTrue(executed[1].startswith("VACUUM"))

    def test_print_results_outputs_tab_separated_rows(self):
        buf = StringIO()
        cur = MagicMock()
        cur.description = [("col_a",), ("col_b",)]
        cur.__iter__ = lambda self: iter([(1, "x"), (2, "y")])

        sql_runner._print_results(cur, buf)

        lines = buf.getvalue().strip().split("\n")
        self.assertEqual(lines[0], "col_a\tcol_b")
        self.assertEqual(lines[1], "1\tx")
        self.assertEqual(lines[2], "2\ty")

    def test_cli_runs_sql_file_and_returns_non_zero_on_execution_error(self):
        from poc.run_sql_file import main

        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "fail.sql"
            sql_path.write_text("SELECT 1;\n", encoding="utf-8")

            fake_settings = SimpleNamespace(bloat_rounds=5)

            with (
                patch("poc.run_sql_file.load_settings", return_value=fake_settings),
                patch.object(sql_runner, "run_sql_file", side_effect=RuntimeError("execution error")),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main([str(sql_path)])
                self.assertNotEqual(ctx.exception.code, 0)

    def test_split_statements_preserves_dollar_quoted_blocks(self):
        sql = (
            "DO $$\n"
            "BEGIN\n"
            "  FOR i IN 1..5 LOOP\n"
            "    INSERT INTO t VALUES (i);\n"
            "  END LOOP;\n"
            "END $$;\n"
            "VACUUM (ANALYZE) t;\n"
        )
        stmts = sql_runner._split_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertTrue(stmts[0].startswith("DO $$"))
        self.assertIn("INSERT INTO t VALUES (i);", stmts[0])
        self.assertIn("END $$", stmts[0])
        self.assertEqual(stmts[1], "VACUUM (ANALYZE) t")

    def test_split_statements_handles_escaped_single_quotes(self):
        sql = "SELECT 'it''s a value';\nSELECT 2;\n"
        stmts = sql_runner._split_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertEqual(stmts[0], "SELECT 'it''s a value'")

    def test_split_statements_rejects_unterminated_string(self):
        with self.assertRaises(ValueError):
            sql_runner._split_statements("SELECT 'unterminated;\n")

    def test_split_statements_rejects_unterminated_dollar_quote(self):
        with self.assertRaises(ValueError):
            sql_runner._split_statements("DO $$ BEGIN NULL; END;\n")

    def test_split_statements_preserves_block_comments_with_semicolons(self):
        sql = "SELECT 1; /* block; comment */ SELECT 2;\n"
        stmts = sql_runner._split_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertEqual(stmts[0], "SELECT 1")
        self.assertIn("/* block; comment */", stmts[1])

    def test_split_statements_rejects_unterminated_block_comment(self):
        with self.assertRaises(ValueError):
            sql_runner._split_statements("SELECT 1; /* never closed\n")

    def test_substitution_ignores_partial_identifier_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "partial.sql"
            sql_path.write_text(
                ":BLOAT_ROUNDS :BLOAT_ROUNDS_EXTRA\n",
                encoding="utf-8",
            )
            result = sql_runner.load_and_substitute(sql_path, {"BLOAT_ROUNDS": "5"})
            self.assertIn("5", result)
            self.assertIn(":BLOAT_ROUNDS_EXTRA", result)

    def test_substitution_preserves_postgres_type_casts(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "cast.sql"
            sql_path.write_text(
                "SELECT now()::text, '{\"a\":1}'::jsonb, :BLOAT_ROUNDS;\n",
                encoding="utf-8",
            )
            result = sql_runner.load_and_substitute(sql_path, {"BLOAT_ROUNDS": "5"})
            self.assertIn("::text", result)
            self.assertIn("::jsonb", result)
            self.assertNotIn(":text", result.replace("::text", ""))
            self.assertNotIn(":jsonb", result.replace("::jsonb", ""))

    def test_substitution_does_not_replace_type_cast_even_when_var_named_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "cast_collision.sql"
            sql_path.write_text(
                "SELECT now()::text, :text;\n",
                encoding="utf-8",
            )
            result = sql_runner.load_and_substitute(sql_path, {"text": "foo"})
            self.assertIn("::text", result)
            self.assertIn("foo", result)
            self.assertNotIn(":text", result.replace("::text", ""))

    def test_split_statements_preserves_whitespace_after_line_comment(self):
        sql = "SELECT 1-- comment\nFROM pg_class;\n"
        stmts = sql_runner._split_statements(sql)
        self.assertEqual(len(stmts), 1)
        self.assertEqual(stmts[0], "SELECT 1\nFROM pg_class")

    def test_split_statements_handles_multiple_line_comments(self):
        sql = "SELECT a-- x\n,b-- y\nFROM t;\n"
        stmts = sql_runner._split_statements(sql)
        self.assertEqual(len(stmts), 1)
        self.assertIn("SELECT a\n,b\nFROM t", stmts[0])


if __name__ == "__main__":
    unittest.main()
