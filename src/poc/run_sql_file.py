from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import sql_runner
from .config import load_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Execute a SQL file against the configured database.",
    )
    parser.add_argument(
        "sql_file",
        type=Path,
        help="Path to the SQL file to execute.",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Variable substitution (repeatable). Replaces :KEY with VALUE in SQL.",
    )
    args = parser.parse_args(argv)

    sql_path = args.sql_file
    if not sql_path.is_file():
        print(f"ERROR: SQL file not found: {sql_path}", file=sys.stderr)
        sys.exit(1)

    settings = load_settings()

    variables: dict[str, str] = {"BLOAT_ROUNDS": str(settings.bloat_rounds)}
    for pair in args.var:
        if "=" not in pair:
            parser.error(f"--var requires KEY=VALUE, got: {pair}")
        key, _, value = pair.partition("=")
        variables[key] = value

    try:
        sql_runner.run_sql_file(sql_path, settings, variables, output=sys.stdout)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
