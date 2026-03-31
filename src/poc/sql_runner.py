from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import IO

from .db import connect
from .config import Settings


_UTILITY_RE = re.compile(r"^\s*(VACUUM|REINDEX|CLUSTER)\b", re.IGNORECASE)


_VAR_RE = re.compile(r"(?<!:)(?<!\w):([a-zA-Z_]\w*)(?!\w)")


def load_and_substitute(sql_path: Path, variables: dict[str, str]) -> str:
    text = sql_path.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        return variables.get(match.group(1), match.group(0))

    return _VAR_RE.sub(_replace, text)


_DOLLAR_TAG_RE = re.compile(r"\$([a-zA-Z_]\w*)?\$")


def _split_statements(sql: str) -> list[str]:
    stmts: list[str] = []
    current: list[str] = []
    pos = 0
    length = len(sql)

    while pos < length:
        ch = sql[pos]

        tag_match = _DOLLAR_TAG_RE.match(sql, pos)
        if tag_match:
            tag = tag_match.group(0)
            end = sql.find(tag, pos + len(tag))
            if end == -1:
                raise ValueError(f"unterminated dollar-quoted string: {tag}")
            current.append(sql[pos : end + len(tag)])
            pos = end + len(tag)
            continue

        if ch == "'":
            start = pos
            pos += 1
            while pos < length:
                next_q = sql.find("'", pos)
                if next_q == -1:
                    raise ValueError("unterminated single-quoted string")
                if next_q + 1 < length and sql[next_q + 1] == "'":
                    pos = next_q + 2
                    continue
                current.append(sql[start : next_q + 1])
                pos = next_q + 1
                break
            continue

        if ch == "-" and pos + 1 < length and sql[pos + 1] == "-":
            end = sql.find("\n", pos)
            if end == -1:
                pos = length
            else:
                current.append("\n")
                pos = end + 1
            continue

        if ch == "/" and pos + 1 < length and sql[pos + 1] == "*":
            end = sql.find("*/", pos + 2)
            if end == -1:
                raise ValueError("unterminated block comment")
            current.append(sql[pos : end + 2])
            pos = end + 2
            continue

        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
            pos += 1
            continue

        current.append(ch)
        pos += 1

    stmt = "".join(current).strip()
    if stmt:
        stmts.append(stmt)

    return stmts


def _is_utility(stmt: str) -> bool:
    return bool(_UTILITY_RE.match(stmt))


def _print_results(cur, output: IO[str]) -> None:
    cols = [desc[0] for desc in cur.description]
    print("\t".join(cols), file=output)
    for row in cur:
        print("\t".join(str(v) for v in row), file=output)


def run_sql_file(
    sql_path: Path,
    settings: Settings,
    variables: dict[str, str],
    output: IO[str] | None = None,
) -> None:
    sql = load_and_substitute(sql_path, variables)
    conn = connect(settings)

    try:
        statements = _split_statements(sql)
        for stmt in statements:
            if _is_utility(stmt):
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.autocommit = False
            else:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                    if output is not None and cur.description is not None:
                        _print_results(cur, output)
                conn.commit()
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
