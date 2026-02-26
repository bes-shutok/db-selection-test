from __future__ import annotations

from pathlib import Path

from psycopg import sql

from .config import load_settings
from .db import connect


def copy_csv(cur, table: str, columns: list[str], file_path: Path) -> None:
    query = sql.SQL(
        "COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
    )
    with file_path.open("r", encoding="utf-8") as handle:
        with cur.copy(query) as copy:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                copy.write(chunk)


def main() -> None:
    settings = load_settings()

    files = {
        "profiles": settings.data_dir / "profiles.csv",
        "profile_properties": settings.data_dir / "profile_properties.csv",
        "consent": settings.data_dir / "consent.csv",
        "message_events": settings.data_dir / "message_events.csv",
    }

    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            f"missing generated CSV files: {missing}; expected under {settings.data_dir}"
        )

    with connect(settings, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE message_events, consent, profile_properties, profiles RESTART IDENTITY CASCADE"
            )

            print("loading profiles...")
            copy_csv(
                cur,
                "profiles",
                [
                    "tenant_id",
                    "profile_id",
                    "status",
                    "country",
                    "language",
                    "created_at",
                    "updated_at",
                ],
                files["profiles"],
            )

            print("loading profile_properties...")
            copy_csv(
                cur,
                "profile_properties",
                [
                    "tenant_id",
                    "profile_id",
                    "custom_properties",
                    "properties_version",
                    "updated_at",
                ],
                files["profile_properties"],
            )

            print("loading consent...")
            copy_csv(
                cur,
                "consent",
                [
                    "tenant_id",
                    "profile_id",
                    "channel",
                    "purpose",
                    "state",
                    "updated_at",
                    "source",
                ],
                files["consent"],
            )

            print("loading message_events...")
            copy_csv(
                cur,
                "message_events",
                [
                    "tenant_id",
                    "profile_id",
                    "campaign_id",
                    "channel",
                    "event_type",
                    "event_time",
                    "attributes",
                ],
                files["message_events"],
            )

            cur.execute("ANALYZE")
        conn.commit()

    print("load complete")


if __name__ == "__main__":
    main()
