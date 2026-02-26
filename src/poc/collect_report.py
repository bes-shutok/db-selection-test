from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from .config import load_settings


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _markdown_cell(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def csv_shape(path: Path) -> tuple[list[str], int]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return [], 0

        row_count = sum(1 for _ in reader)
    return header, row_count


def text_line_count(path: Path) -> int:
    raw = path.read_text(encoding="utf-8")
    if not raw:
        return 0
    return len(raw.splitlines())


def append_timing_section(report_lines: list[str], timings_summary: Path) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv_rows(timings_summary):
        grouped[row["query_type"]].append(row)

    report_lines.extend(
        [
            "",
            "## Timing Summary",
        ]
    )

    for query_type in ["read", "write", "complex"]:
        rows = grouped.get(query_type, [])
        if not rows:
            continue
        report_lines.append("")
        report_lines.append(f"### {query_type.title()} Queries")
        report_lines.append("| Query | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) | runs |")
        report_lines.append("|---|---:|---:|---:|---:|---:|")
        for row in sorted(rows, key=lambda x: x["query_name"]):
            report_lines.append(
                f"| {row['query_name']} | {row['p50_ms']} | {row['p95_ms']} | {row['p99_ms']} | {row['mean_ms']} | {row['runs']} |"
            )


def append_bloat_impact_section(
    report_lines: list[str],
    timings_summary_pre: Path,
    timings_summary_post: Path,
    bloat_metrics_pre: Path,
    bloat_metrics_post: Path,
) -> None:
    pre_data: dict[str, dict[str, float]] = {}
    post_data: dict[str, dict[str, float]] = {}

    for row in read_csv_rows(timings_summary_pre):
        pre_data[row["query_name"]] = {
            "p99_ms": float(row["p99_ms"]),
            "p95_ms": float(row["p95_ms"]),
            "mean_ms": float(row["mean_ms"]),
        }

    for row in read_csv_rows(timings_summary_post):
        post_data[row["query_name"]] = {
            "p99_ms": float(row["p99_ms"]),
            "p95_ms": float(row["p95_ms"]),
            "mean_ms": float(row["mean_ms"]),
        }

    degradations = []
    for query_name in sorted(pre_data.keys()):
        if query_name not in post_data:
            continue

        pre_p99 = pre_data[query_name]["p99_ms"]
        post_p99 = post_data[query_name]["p99_ms"]

        if pre_p99 > 0:
            degradation_pct = ((post_p99 - pre_p99) / pre_p99) * 100
        else:
            degradation_pct = 0.0

        degradations.append(
            {
                "query_name": query_name,
                "pre_p99": pre_p99,
                "post_p99": post_p99,
                "degradation_pct": degradation_pct,
            }
        )

    report_lines.extend(
        [
            "",
            "## Bloat Impact Analysis",
            "",
            "### Query Performance Degradation",
            "| Query | Pre-Bloat p99 (ms) | Post-Bloat p99 (ms) | Degradation |",
            "|---|---:|---:|---:|",
        ]
    )

    total_degradation = 0.0
    for item in degradations:
        sign = "+" if item["degradation_pct"] >= 0 else ""
        report_lines.append(
            f"| {item['query_name']} | {item['pre_p99']:.3f} | {item['post_p99']:.3f} | {sign}{item['degradation_pct']:.1f}% |"
        )
        total_degradation += item["degradation_pct"]

    avg_degradation = total_degradation / len(degradations) if degradations else 0.0
    report_lines.extend(
        [
            "",
            f"Average degradation: {avg_degradation:+.1f}%",
            "",
        ]
    )

    if bloat_metrics_pre.exists() and bloat_metrics_post.exists():
        report_lines.append("### Bloat Metrics Summary")
        report_lines.append("")
        report_lines.append("Pre-bloat baseline:")
        report_lines.append("```")
        report_lines.append(bloat_metrics_pre.read_text(encoding="utf-8").strip())
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("Post-bloat:")
        report_lines.append("```")
        report_lines.append(bloat_metrics_post.read_text(encoding="utf-8").strip())
        report_lines.append("```")
        report_lines.append("")

    report_lines.append("### Bloat Impact Interpretation")
    if avg_degradation < 5:
        interpretation = "Excellent - aggressive autovacuum settings are effectively managing bloat"
    elif avg_degradation < 15:
        interpretation = "Good - some bloat accumulation between vacuum cycles, but within acceptable range"
    elif avg_degradation < 30:
        interpretation = "Concerning - autovacuum may not be keeping up with update churn"
    else:
        interpretation = "Critical - significant bloat impact, review autovacuum settings"

    report_lines.append(f"- {interpretation}")
    report_lines.append("")


def append_load_section(
    report_lines: list[str],
    title: str,
    load_summary_path: Path,
    load_phase_summary_path: Path,
    load_executions_path: Path | None = None,
) -> None:
    phase_rows = read_csv_rows(load_phase_summary_path)
    summary_rows = read_csv_rows(load_summary_path)

    report_lines.extend(
        [
            "",
            f"### {title}",
        ]
    )

    if phase_rows:
        phase = phase_rows[0]
        report_lines.append(
            "- load profile: "
            f"workers={phase.get('workers', 'n/a')}, "
            f"warmup_s={phase.get('warmup_seconds', 'n/a')}, "
            f"duration_s={phase.get('duration_seconds', 'n/a')}"
        )
        report_lines.append(
            "- phase totals: "
            f"calls={phase.get('total_calls', 'n/a')}, "
            f"errors={phase.get('total_errors', 'n/a')}, "
            f"overall_qps={phase.get('overall_qps', 'n/a')}"
        )

    # Keep a blank line before pipe-table blocks so markdown renderers
    # parse these rows as tables instead of plain paragraph text.
    report_lines.append("")
    report_lines.append("| Query | calls | errors | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) | qps |")
    report_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in sorted(summary_rows, key=lambda x: x["query_name"]):
        report_lines.append(
            f"| {row['query_name']} | {row['calls']} | {row['errors']} | {row['p50_ms']} | {row['p95_ms']} | {row['p99_ms']} | {row['mean_ms']} | {row['qps']} |"
        )

    if load_executions_path and load_executions_path.exists():
        by_signature: dict[tuple[str, str], int] = defaultdict(int)
        for row in read_csv_rows(load_executions_path):
            status = row.get("status", "").strip()
            if status in {"ok", "ok_retry"}:
                continue
            error_code = (row.get("error_code", "") or "").strip() or status or "n/a"
            error_message = row.get("error_message", "").strip()
            if not error_message:
                if status == "conflict":
                    error_message = (
                        "write_patch_properties optimistic lock conflict "
                        "(0 rows affected after retry)"
                    )
                else:
                    error_message = "(error_message not captured in this run artifact)"
            by_signature[(error_code, error_message)] += 1

        if by_signature:
            report_lines.extend(
                [
                    "",
                    "#### Error Signatures (Top 5)",
                    "| count | sqlstate | message |",
                    "|---:|---|---|",
                ]
            )
            for (error_code, error_message), count in sorted(
                by_signature.items(),
                key=lambda item: (-item[1], item[0][0], item[0][1]),
            )[:5]:
                message_cell = _markdown_cell(error_message)
                if len(message_cell) > 180:
                    message_cell = message_cell[:177] + "..."
                report_lines.append(
                    f"| {count} | {_markdown_cell(error_code)} | {message_cell} |"
                )


def append_pgstat_section(report_lines: list[str], results_dir: Path) -> None:
    csv_files = sorted(results_dir.glob("pg_stat_statements*.csv"))
    status_files = sorted(results_dir.glob("pg_stat_statements*_status.txt"))

    if not csv_files and not status_files:
        return

    report_lines.extend(
        [
            "",
            "## pg_stat_statements",
        ]
    )

    if status_files:
        report_lines.append("")
        report_lines.append("### Capture Status")
        for status_file in status_files:
            status_text = status_file.read_text(encoding="utf-8").strip().splitlines()
            phase_label = status_file.name.replace("pg_stat_statements_", "").replace(
                "_status.txt", ""
            )
            report_lines.append(f"- `{phase_label}`")
            report_lines.append("")
            report_lines.append("```text")
            if status_text:
                report_lines.extend(status_text)
            else:
                report_lines.append("n/a")
            report_lines.append("```")


def append_full_artifact_reflection_section(
    report_lines: list[str], results_dir: Path
) -> None:
    def _select_expected_files(
        primary: list[str], legacy: list[str] | None = None
    ) -> list[str]:
        if not legacy:
            return primary

        primary_present = sum(1 for name in primary if (results_dir / name).exists())
        legacy_present = sum(1 for name in legacy if (results_dir / name).exists())

        if primary_present == len(primary):
            return primary
        if legacy_present == len(legacy):
            return legacy

        primary_ratio = primary_present / len(primary) if primary else 0.0
        legacy_ratio = legacy_present / len(legacy) if legacy else 0.0
        if legacy_ratio > primary_ratio:
            return legacy
        return primary

    specs: list[dict[str, object]] = [
        {
            "title": "Timing Iteration CSV",
            "kind": "csv",
            "required": ["timings_pre_bloat.csv", "timings_post_bloat.csv"],
            "legacy_required": ["timings.csv"],
        },
        {
            "title": "Timing Summary CSV",
            "kind": "csv",
            "required": ["timings_summary_pre_bloat.csv", "timings_summary_post_bloat.csv"],
            "legacy_required": ["timings_summary.csv"],
        },
        {
            "title": "Bloat Metrics",
            "kind": "text",
            "required": ["bloat_metrics_pre.txt", "bloat_metrics_post.txt"],
        },
        {
            "title": "Load Executions CSV",
            "kind": "csv",
            "required": [
                "load_executions_pre_bloat.csv",
                "load_executions_post_bloat.csv",
            ],
            "legacy_required": ["load_executions.csv"],
        },
        {
            "title": "Load Summary CSV",
            "kind": "csv",
            "required": ["load_summary_pre_bloat.csv", "load_summary_post_bloat.csv"],
            "legacy_required": ["load_summary.csv"],
        },
        {
            "title": "Load Phase Summary CSV",
            "kind": "csv",
            "required": [
                "load_phase_summary_pre_bloat.csv",
                "load_phase_summary_post_bloat.csv",
            ],
            "legacy_required": ["load_phase_summary.csv"],
        },
        {
            "title": "pg_stat_statements CSV",
            "kind": "csv",
            "required": [
                "pg_stat_statements_pre_bloat.csv",
                "pg_stat_statements_post_bloat.csv",
            ],
            "legacy_required": ["pg_stat_statements.csv"],
        },
        {
            "title": "pg_stat_statements Status",
            "kind": "text",
            "required": [
                "pg_stat_statements_pre_bloat_status.txt",
                "pg_stat_statements_post_bloat_status.txt",
            ],
            "legacy_required": ["pg_stat_statements_status.txt"],
        },
        {
            "title": "Explain Plans",
            "kind": "text_glob",
            "required_glob": "explain/*.txt",
        },
    ]

    report_lines.extend(
        [
            "",
            "## Full Artifact Reflection",
            "",
            "| Artifact Group | File | Present | Rows/Lines | Columns |",
            "|---|---|---|---:|---|",
        ]
    )

    total_expected = 0
    total_present = 0
    total_empty = 0

    for spec in specs:
        title = str(spec["title"])
        kind = str(spec["kind"])

        if kind == "text_glob":
            pattern = str(spec["required_glob"])
            files = sorted(results_dir.glob(pattern))
            total_expected += 1
            if files:
                total_present += 1
            for path in files:
                rel = path.relative_to(results_dir).as_posix()
                lines = text_line_count(path)
                present = "yes"
                if lines == 0:
                    total_empty += 1
                report_lines.append(f"| {title} | `{rel}` | {present} | {lines} | n/a |")
            if not files:
                report_lines.append(
                    f"| {title} | `{pattern}` | no | 0 | n/a |"
                )
            continue

        primary_required = [str(name) for name in spec.get("required", [])]
        legacy_required_raw = spec.get("legacy_required")
        legacy_required = (
            [str(name) for name in legacy_required_raw]
            if isinstance(legacy_required_raw, list)
            else None
        )
        required = _select_expected_files(primary_required, legacy_required)
        total_expected += len(required)
        for name in required:
            path = results_dir / name
            if path.exists():
                total_present += 1
                if kind == "csv":
                    header, row_count = csv_shape(path)
                    columns = ", ".join(header) if header else "(no header)"
                    if row_count == 0:
                        total_empty += 1
                    report_lines.append(
                        f"| {title} | `{name}` | yes | {row_count} | {_markdown_cell(columns)} |"
                    )
                else:
                    lines = text_line_count(path)
                    if lines == 0:
                        total_empty += 1
                    report_lines.append(
                        f"| {title} | `{name}` | yes | {lines} | n/a |"
                    )
            else:
                report_lines.append(
                    f"| {title} | `{name}` | no | 0 | n/a |"
                )

    coverage_pct = (total_present / total_expected * 100.0) if total_expected else 0.0
    report_lines.extend(
        [
            "",
            f"- artifact presence: {total_present}/{total_expected} ({coverage_pct:.1f}%)",
            f"- empty artifacts (present but 0 rows/lines): {total_empty}",
        ]
    )


def main() -> None:
    settings = load_settings()

    timings_summary_pre = settings.results_dir / "timings_summary_pre_bloat.csv"
    timings_summary_post = settings.results_dir / "timings_summary_post_bloat.csv"
    timings_summary_legacy = settings.results_dir / "timings_summary.csv"

    load_summary_pre = settings.results_dir / "load_summary_pre_bloat.csv"
    load_summary_post = settings.results_dir / "load_summary_post_bloat.csv"
    load_summary_legacy = settings.results_dir / "load_summary.csv"

    load_executions_pre = settings.results_dir / "load_executions_pre_bloat.csv"
    load_executions_post = settings.results_dir / "load_executions_post_bloat.csv"
    load_executions_legacy = settings.results_dir / "load_executions.csv"

    load_phase_summary_pre = settings.results_dir / "load_phase_summary_pre_bloat.csv"
    load_phase_summary_post = settings.results_dir / "load_phase_summary_post_bloat.csv"
    load_phase_summary_legacy = settings.results_dir / "load_phase_summary.csv"

    has_bloat_timing = timings_summary_pre.exists() and timings_summary_post.exists()
    has_legacy_timing = timings_summary_legacy.exists()

    has_bloat_load = (
        load_summary_pre.exists()
        and load_summary_post.exists()
        and load_phase_summary_pre.exists()
        and load_phase_summary_post.exists()
    )
    has_legacy_load = load_summary_legacy.exists() and load_phase_summary_legacy.exists()

    if not (has_bloat_timing or has_legacy_timing or has_bloat_load or has_legacy_load):
        raise FileNotFoundError(
            "missing result summaries: expected at least timing or load summary artifacts "
            f"under {settings.results_dir}"
        )

    metadata_path = settings.data_dir / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    report_lines = [
        "# CRM PostgreSQL POC Summary",
        "",
        "## Run Context",
        f"- run_id: `{settings.run_id}`",
        f"- data_scale: `{settings.data_scale}`",
        f"- profile_count: `{settings.profile_count}`",
        f"- event_count: `{settings.event_count}`",
        f"- query_run_profile: `{settings.query_run_profile}`",
    ]

    if metadata:
        report_lines.append(f"- generated_at: `{metadata.get('generated_at', 'n/a')}`")

    if has_bloat_timing:
        append_timing_section(report_lines, timings_summary_pre)
        append_bloat_impact_section(
            report_lines,
            timings_summary_pre,
            timings_summary_post,
            settings.results_dir / "bloat_metrics_pre.txt",
            settings.results_dir / "bloat_metrics_post.txt",
        )
    elif has_legacy_timing:
        append_timing_section(report_lines, timings_summary_legacy)

    if has_bloat_load or has_legacy_load:
        report_lines.extend(
            [
                "",
                "## Load Throughput Summary (QPS)",
                "- QPS formula: calls / measured phase duration seconds.",
                "- Latency p50/p95/p99/mean are computed from successful calls only (`ok`, `ok_retry`).",
            ]
        )

        if has_bloat_load:
            append_load_section(
                report_lines,
                "Pre-Bloat Load Results",
                load_summary_pre,
                load_phase_summary_pre,
                load_executions_pre,
            )
            append_load_section(
                report_lines,
                "Post-Bloat Load Results",
                load_summary_post,
                load_phase_summary_post,
                load_executions_post,
            )
        else:
            append_load_section(
                report_lines,
                "Load Results",
                load_summary_legacy,
                load_phase_summary_legacy,
                load_executions_legacy,
            )

    append_pgstat_section(report_lines, settings.results_dir)

    explain_dir = settings.results_dir / "explain"
    explain_files = sorted(explain_dir.glob("*.txt"))
    report_lines.extend(
        [
            "",
            "## Explain Artifacts",
        ]
    )
    if explain_files:
        report_lines.append(f"- plans captured: `{len(explain_files)}`")
    else:
        report_lines.append("- none")

    append_full_artifact_reflection_section(report_lines, settings.results_dir)

    report_lines.extend(
        [
            "",
            "## Notes",
            "- Iteration timings remain useful for deterministic p50/p95/p99 trend checks.",
            "- Load-mode QPS shows concurrent throughput magnitude for each phase.",
            "- Final pass/fail thresholds are DBA-owned (p95/p99 and CPU/memory criteria).",
        ]
    )

    summary_path = settings.results_dir / "summary.md"
    summary_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"report written: {summary_path}")


if __name__ == "__main__":
    main()
