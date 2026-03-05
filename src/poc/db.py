from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql

from .config import Settings


def connect(settings: Settings, autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        autocommit=autocommit,
    )
    apply_session_settings(conn, settings)
    return conn


def apply_session_settings(conn: psycopg.Connection, settings: Settings) -> None:
    statements: list[sql.Composed] = []
    if settings.db_session_role:
        statements.append(
            sql.SQL("SET ROLE {}").format(sql.Identifier(settings.db_session_role))
        )
    if settings.db_schema:
        statements.append(
            sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(settings.db_schema)
            )
        )

    if not statements:
        return

    previous_autocommit = conn.autocommit
    if not previous_autocommit:
        conn.autocommit = True

    try:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
    finally:
        if not previous_autocommit:
            conn.autocommit = previous_autocommit


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
