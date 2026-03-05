from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from faker import Faker

from .config import load_settings
from .db import ensure_dirs


faker = Faker()
RNG = random.Random(42)
NP_RNG = np.random.default_rng(42)


def sporty_id(seq: int, prefix: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"{ts}{prefix}{seq:08d}"


def weighted_choice(values: list[str], weights: list[float]) -> str:
    return RNG.choices(values, weights=weights, k=1)[0]


def random_time(within_days: int) -> datetime:
    seconds = RNG.randint(0, within_days * 24 * 60 * 60)
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def generate_profiles(path: Path, profile_count: int) -> list[tuple[str, str]]:
    tenant_main = "260217000000ups00000001"
    tenant_secondary = "260217000000ups00000002"

    countries = ["NG", "KE", "GH", "TZ", "UG", "ZA", "CM", "CI"]
    country_w = [0.31, 0.19, 0.14, 0.10, 0.08, 0.08, 0.05, 0.05]

    languages = ["en", "fr", "sw", "pt", "ar", "ha"]
    language_w = [0.68, 0.12, 0.08, 0.06, 0.04, 0.02]

    rows: list[tuple[str, str]] = []

    now_utc = datetime.now(timezone.utc)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "tenant_id",
            "profile_id",
            "status",
            "country",
            "language",
            "created_at",
            "updated_at",
        ])

        for i in range(1, profile_count + 1):
            tenant_id = tenant_main if RNG.random() < 0.99 else tenant_secondary
            profile_id = sporty_id(i, "prf0")
            status = "ACTIVE" if RNG.random() < 0.96 else "DELETED"
            country = weighted_choice(countries, country_w)
            language = weighted_choice(languages, language_w)
            created_at = random_time(365)
            updated_at = min(
                created_at + timedelta(days=RNG.randint(0, 180)),
                now_utc,
            )

            writer.writerow([
                tenant_id,
                profile_id,
                status,
                country,
                language,
                created_at.isoformat(),
                updated_at.isoformat(),
            ])
            rows.append((tenant_id, profile_id))

            if i % 100_000 == 0:
                print(f"generated profiles: {i}")

    return rows


def generate_profile_properties(path: Path, profiles: list[tuple[str, str]]) -> None:
    plans = ["free", "pro", "vip"]
    plan_w = [0.67, 0.25, 0.08]

    segments = ["high_value", "retention_push", "reactivation", "inactive", "new"]
    segment_w = [0.10, 0.22, 0.21, 0.17, 0.30]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "tenant_id",
            "profile_id",
            "custom_properties",
            "properties_version",
            "updated_at",
        ])

        for idx, (tenant_id, profile_id) in enumerate(profiles, start=1):
            vip = RNG.random() < 0.11
            plan = weighted_choice(plans, plan_w)
            segment = weighted_choice(segments, segment_w)
            deposit_bucket = weighted_choice(["low", "mid", "high"], [0.56, 0.31, 0.13])
            risk_band = weighted_choice(["low", "medium", "high"], [0.42, 0.45, 0.13])

            payload = {
                "plan": plan,
                "vip": vip,
                "vip_level": weighted_choice(["bronze", "silver", "gold"], [0.55, 0.31, 0.14]),
                "segment": segment,
                "deposit": {
                    "bucket": deposit_bucket,
                    "last_at": random_time(90).isoformat(),
                },
                "risk_band": risk_band,
                "tags": RNG.sample(
                    ["sportsbook", "casino", "high_value", "reactivation", "cross_sell"],
                    k=RNG.randint(1, 3),
                ),
                "last_bet_at": random_time(60).isoformat(),
            }

            writer.writerow([
                tenant_id,
                profile_id,
                json.dumps(payload, separators=(",", ":")),
                RNG.randint(1, 8),
                datetime.now(timezone.utc).isoformat(),
            ])

            if idx % 100_000 == 0:
                print(f"generated profile_properties: {idx}")


def generate_consent(path: Path, profiles: list[tuple[str, str]]) -> None:
    channels = ["email", "sms", "push"]
    purposes = ["marketing", "transactional", "security"]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "tenant_id",
            "profile_id",
            "channel",
            "purpose",
            "state",
            "updated_at",
            "source",
        ])

        idx = 0
        for tenant_id, profile_id in profiles:
            for channel in channels:
                for purpose in purposes:
                    if purpose == "marketing":
                        state = weighted_choice(["opted_in", "opted_out", "unknown"], [0.49, 0.32, 0.19])
                    else:
                        state = weighted_choice(["opted_in", "opted_out"], [0.90, 0.10])

                    writer.writerow([
                        tenant_id,
                        profile_id,
                        channel,
                        purpose,
                        state,
                        random_time(120).isoformat(),
                        weighted_choice(["api", "import", "admin", "migration"], [0.45, 0.30, 0.15, 0.10]),
                    ])
                    idx += 1

                    if idx % 500_000 == 0:
                        print(f"generated consent rows: {idx}")


def generate_message_events(path: Path, profiles: list[tuple[str, str]], event_count: int) -> None:
    campaign_pool = [sporty_id(i, "cmp0") for i in range(1, 201)]

    profile_idx = NP_RNG.integers(0, len(profiles), size=event_count)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "tenant_id",
            "profile_id",
            "campaign_id",
            "channel",
            "event_type",
            "event_time",
            "attributes",
        ])

        for i in range(event_count):
            tenant_id, profile_id = profiles[int(profile_idx[i])]
            channel = weighted_choice(["email", "sms", "push", "inbox"], [0.39, 0.34, 0.17, 0.10])
            event_type = weighted_choice(["sent", "delivered", "failed", "opened", "clicked"], [0.35, 0.30, 0.08, 0.17, 0.10])

            attributes = {
                "provider": weighted_choice(["twilio", "sparkpost", "internal", "seed"], [0.31, 0.24, 0.34, 0.11]),
                "template_id": f"tmpl_{RNG.randint(1, 250)}",
                "delivery_bucket": weighted_choice(["normal", "priority"], [0.91, 0.09]),
                "region": weighted_choice(["eu", "af", "me"], [0.36, 0.54, 0.10]),
            }

            writer.writerow([
                tenant_id,
                profile_id,
                campaign_pool[RNG.randint(0, len(campaign_pool) - 1)],
                channel,
                event_type,
                random_time(120).isoformat(),
                json.dumps(attributes, separators=(",", ":")),
            ])

            if (i + 1) % 1_000_000 == 0:
                print(f"generated message_events: {i + 1}")


def main() -> None:
    settings = load_settings()
    ensure_dirs(settings.data_dir)

    profiles_csv = settings.data_dir / "profiles.csv"
    profile_properties_csv = settings.data_dir / "profile_properties.csv"
    consent_csv = settings.data_dir / "consent.csv"
    message_events_csv = settings.data_dir / "message_events.csv"

    print(f"run_id={settings.run_id} scale={settings.data_scale}")
    print(f"profiles={settings.profile_count} events={settings.event_count}")

    profiles = generate_profiles(profiles_csv, settings.profile_count)
    generate_profile_properties(profile_properties_csv, profiles)
    generate_consent(consent_csv, profiles)
    generate_message_events(message_events_csv, profiles, settings.event_count)

    metadata = {
        "run_id": settings.run_id,
        "data_scale": settings.data_scale,
        "profile_count": settings.profile_count,
        "event_count": settings.event_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "profiles": str(profiles_csv),
            "profile_properties": str(profile_properties_csv),
            "consent": str(consent_csv),
            "message_events": str(message_events_csv),
        },
    }
    (settings.data_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"data generated in {settings.data_dir}")


if __name__ == "__main__":
    main()
