# AGENTS.md

## Core Concepts
- CRM PostgreSQL POC: standalone database validation project for CRM-like workloads.
- Lean scope: minimal schema/query surface that still captures JSONB-heavy and OLAP-ish behavior.
- Baseline vs stretch: two data scales used to observe behavior under growth.
- Bloat phase: intentional update-heavy workload to surface MVCC/maintenance effects.

## Repository Purpose
This repository is for PostgreSQL validation only. It is not a CRM service implementation and not an MVP codebase.

Primary objective:
- validate schema + synthetic data + representative queries and provide artifacts for DBA review.

## CRM Context (Why this POC exists)
CRM architecture is service-oriented with six domains:
1. User Platform Service
2. Campaign Service
3. Event Ingestion Service
4. Control Plane Service
5. Messaging Service
6. Analytics Service

This POC models only the operational patterns needed to evaluate PostgreSQL for:
- dynamic profile attributes (JSONB)
- consent lookups/updates
- event aggregations and OLAP-ish reads

## Scope Boundaries
In scope tables:
- `profiles`
- `profile_properties`
- `consent`
- `message_events`

Out of scope for this POC:
- full campaign/journey model
- control plane admin entities
- event bus/outbox semantics
- API/service layer behavior
- full analytics warehouse design

## Design Assumptions
1. Synthetic data only.
2. Baseline scale: `100k profiles + 5M events`.
3. Stretch scale: `500k profiles + 20M events`.
4. Bloat focus:
- primary: `profile_properties`
- secondary: `consent`
- no intentional bloat on `message_events`.
5. Local Docker run is baseline/correctness only; deeper stress/perf validation is mainly on DBA infra.
6. Success thresholds (p95/p99, CPU, memory criteria) are DBA-owned inputs.
7. Consent behavior/performance validation baseline in this project is PostgreSQL `16.8`.

## Project Structure
- `sql/`: DDL, indexes, query catalog, bloat workload
- `src/poc/`: Python generation/load/run/report modules
- `scripts/`: orchestration scripts for local and DBA environments
- `data/`: generated CSV/metadata (run-specific)
- `results/`: timings, explain plans, summaries (run-specific)
- `docs/`: project documentation and execution notes

## Standard Workflow
1. `cp .env.example .env`
2. `uv sync`
3. `docker compose up -d`
4. `./scripts/run_local.sh`

DBA environment replay:
- configure `.env` with DBA connection
- run `./scripts/run_on_dba_env.sh`

## Coding and Data Rules
1. Keep scripts idempotent where possible.
2. Keep generated data deterministic (fixed RNG seed) unless a change is intentional.
3. Add new query scenarios as named queries in `sql/004_queries_core.sql` or `sql/005_queries_complex.sql`.
4. Keep bloat logic in `sql/006_bloat_workload.sql` and do not mix with core query scripts.
5. Maintain `src/` layout compatibility (`PYTHONPATH` is set by scripts).
6. When runbook steps change, keep `README.md`, `docs/CRM_POC_SPEC.md`, and script behavior aligned in the same patch.
7. Ensure runbook docs include concrete artifact output location patterns (`results/$RUN_ID/`), not placeholder-only wording.

## Artifact Expectations
For each run, provide:
1. timing artifacts under `results/$RUN_ID/`:
   - baseline mode: `timings.csv`, `timings_summary.csv`
   - bloat mode: `timings_pre_bloat.csv`, `timings_summary_pre_bloat.csv`, `timings_post_bloat.csv`, `timings_summary_post_bloat.csv`
2. `explain/*.txt` for complex queries (captured in baseline/pre-bloat phase)
3. `summary.md`

These artifacts are the handoff contract for DBA analysis.

## Extension Guidance
If expanding scope, prefer this order:
1. Add query variants first (new workload signal)
2. Add synthetic data dimensions/distributions
3. Add table/index structures only when needed to support validated use cases

Keep the project focused on proving/disproving PostgreSQL fit for CRM operational + OLAP-ish patterns.

## Version Pinning
1. Keep Docker image pinned to an explicit PostgreSQL minor tag (`postgres:16.8`) unless DBA requests upgrade.
2. Keep Python runtime pinned via `.python-version` (`3.14.2`).
3. Keep all Python dependencies pinned to exact versions in `pyproject.toml` (`==`).
4. Keep `uv` pinned to version `0.10.0` for reproducible lock resolution.
5. Any version upgrade must update README pinned matrix and run artifacts notes.

## LLM Instruction Rules

### Section 1: Reusable engineering rules (Java/Kotlin ecosystem)
Rules that apply broadly to engineering work across projects.

1. **Verify documentation claims against executable code before publishing**
   - When a document says "actual logic," confirm loop structure, state resets, and artifact naming in the current implementation.

2. **Separate measured facts from external estimates**
   - Label directly measured results and externally sourced projections explicitly, and do not merge them into a single conclusion table without qualifiers.

3. **Use syntax examples that are valid in non-trigger SQL**
   - In plain SQL `RETURNING`, never use trigger-only `OLD`/`NEW` references; return target-table expressions or use CTEs when prior values are required.

4. **Guard extension function usage by extension existence checks**
   - Before invoking extension-provided functions, check installation status and call conditionally.

5. **Quantify workload churn with both volume and per-row average**
   - When documenting update-heavy workloads, report both total update operations and average updates per row with an explicit formula.

### Section 2: Repository Style and Conventions
Rules for consistency in this repository only.

1. **Use publication-safe cross-document references in artifact docs**
   - In `docs/` narrative text intended for external publication, reference documents as human-readable title plus filename in parentheses.
   - Avoid repository path prefixes such as `docs/...` for those references.

2. **Keep run-mode docs synchronized with script behavior**
   - When run flow changes, update both `run_local.sh`/`run_on_dba_env.sh` behavior descriptions and artifact naming examples in the same patch.

3. **Validate extension usage claims against repository execution paths**
   - Do not state that extensions are used by automated Python flows unless code under `src/poc/` actually reads those extension views/functions.

4. **Prefer explicit typing in Python-to-SQL parameter binding when ambiguous**
   - Use explicit value casts or SQL placeholder casts where driver inference can be unclear.

5. **Keep terminology sections mandatory in non-trivial docs**
   - Every substantial document under `docs/` must start with `Core Concepts`, `Key Concepts`, or `Terminology`, and later sections must reuse those terms.

6. **Synchronize run-driven documentation updates end-to-end**
   - When refreshing performance docs to a new run, update run IDs, metrics tables, appendix numbers, metadata, and related references in the same patch.

7. **Use restrained emphasis in publication-facing docs**
   - Prefer plain text for routine statements; reserve bold/emojis for a small number of high-signal caveats or decisions.

8. **Quote JSON-valued `.env` examples for shell-sourced workflows**
   - When `.env` is sourced by shell scripts, wrap JSON example values in outer single quotes so internal JSON quotes are preserved.

9. **Preserve complete multi-line status details in handoff summaries**
   - If a status artifact can contain multiple events (for example, reset success followed by capture failure), surface all lines in summary outputs instead of only the first line.

10. **Document load magnitude with explicit throughput formulas**
   - In load-mode docs and summaries, report both per-query and phase-level QPS and state the formula with units (`calls / measured duration seconds`), identifying QPS as a derived metric.

11. **Preserve document structure during metric refreshes**
   - When updating performance docs to a new run, keep existing analytical sections and context unless content is incorrect or the user asks to remove it.
   - If removal is ambiguous, ask before deleting substantive content.

12. **Prefer reader-facing runtime parameters over env variable names in publication docs**
   - In publication-facing analysis docs, present concrete run parameters (for example worker count, warmup seconds, and measured duration) instead of internal variable identifiers unless explicitly requested.

13. **Separate load latency quality from load error quality**
   - In load artifacts and summaries, compute latency percentiles/means from successful calls only (`ok`, `ok_retry`) and report failures via explicit error counts plus error signatures.

14. **Represent optimistic-lock conflicts as explicit signatures**
   - In load execution artifacts and summaries, treat handled optimistic-lock outcomes (for example `status=conflict`) as explicit signatures with non-empty code/message fields.
   - Do not allow conflict rows to collapse into `n/a` or placeholder-only error signature text.

15. **Use conservative local PostgreSQL memory tuning first**
   - For laptop/local Docker guidance, treat `work_mem` as per-operation memory; reduce `LOAD_WORKERS` and heavy-query mix before suggesting higher `PG_WORK_MEM`.
   - When `53100` appears in load artifacts, classify it as disk/temp-file pressure first and verify this path before attributing failures to RAM.

16. **Qualify topology and capacity claims by environment**
   - In publication-facing performance docs, do not claim production topology outcomes (for example, "no replicas needed") from local runs unless explicitly validated.
   - When citing local throughput/stability, label it as local and separate dedicated-server expectations (higher workers, stronger load intensity) as projections.

17. **Keep Markdown tables parser-safe**
   - Ensure a blank line before each table block when it follows paragraph text or a label line (for example, `Key Differences:`) to avoid flattened rendering in stricter Markdown parsers.

18. **Re-verify external link accessibility when refreshing publication docs**
   - Before keeping or adding claims such as "source unavailable", "403", or "link inaccessible", re-check the cited URL in the current session and update verification notes with the current date.
   - Do not preserve stale accessibility caveats after links become reachable.

19. **Keep summary artifact listing single-sourced**
   - In generated run summaries, avoid listing the same artifact files in multiple sections.
   - Use one authoritative per-file inventory section; keep narrative sections status-focused or aggregate-only.

20. **Back multi-run comparisons with complete per-run evidence**
   - When a document compares multiple runs, list every run ID used and include exact artifact file references for each run.
   - For derived metrics tables, also include the raw per-run phase/source values used to compute them.

21. **Keep artifact reflection checks run-mode aware and group-based**
   - In `summary.md` artifact reflection, accept both pre/post-bloat and legacy single-file naming for supported run modes.
   - For glob-based artifact groups (for example explain plans), count expected presence at the group level so missing groups reduce coverage.

22. **Keep default-version SQL catalogs canonical and unsuffixed**
   - When the repository baseline PostgreSQL version changes, keep `sql/004_queries_core.sql` and `sql/005_queries_complex.sql` as the new default catalogs.
   - Move non-default version variants to explicit suffixed files (for example `*_pg18.sql`) and update override examples in docs in the same patch.

23. **Document SQL RETURNING consumption contracts at the query definition**
   - When runner logic consumes only a subset of returned columns, document the consumed column positions/names directly in the SQL file comments.
   - If placeholder fields are retained for shape parity (for example `NULL AS old_*`), label them as observability-only and non-functional.

24. **Keep baseline-version docs single-version outside comparison reports**
   - Outside explicit comparison documents, describe only the current baseline PostgreSQL version (`16.8`) to avoid mixed-version guidance.
   - Place cross-version (`16.x` vs `18.x`) analysis only in `PERFORMANCE_ANALYSIS_POSTGRESQL_VS_MYSQL.md`.

25. **Keep external DBA runbooks self-contained and path-neutral**
   - For publication-targeted docs that are copied outside the repository (for example algorithm/runbook docs), avoid local repository paths and implementation file references.
   - Include complete workload SQL text in-document (no placeholder joins/ellipsis) when the document is intended for DBA replay.

26. **Anonymize people and internal org identifiers in shared docs**
   - In communication logs and publication-facing docs, avoid naming specific individuals or internal department codes unless explicitly required by the user.
   - Prefer role-based wording (for example, `CRM engineering representatives`, `DBA representatives`).

27. **Classify sensitivity conservatively and evidence-first**
   - Do not mark content as company-sensitive solely because it is recommendation narrative; require concrete non-public details (for example named people, internal codes, credentials, explicit rollout commitments, or private infrastructure specifics).
   - When flagging sensitivity, cite the exact lines that make it sensitive.

28. **Keep workflow narrative separate from executable SQL examples**
   - In algorithm/runbook docs, keep phase sections focused on step flow and place concrete DDL/COPY/seed examples under the SQL reference section.
   - If a phase needs those examples for clarity, add a short cross-reference instead of duplicating SQL blocks in the phase narrative.

29. **Label sampled load data as excerpts with full-scale context**
   - When showing example CSV rows from generated datasets, explicitly state that rows are excerpts and include the total generated row counts for each shown table.
   - When relevant, distinguish generated row counts from additional static seed rows so readers can reconcile final table cardinality.

30. **Keep schema-introspection SQL aligned with runtime schema context**
   - For diagnostics queries (`pg_stat_user_tables`, `pg_stat_user_indexes`, TOAST/relnamespace joins), do not hardcode `public`; scope by `current_schema()` or explicit runtime schema selection.
   - Apply the same schema-scoping rule to summary artifacts so non-`public` runs do not produce header-only metric files.

31. **Use `psql` semantics for SQL catalogs that include utility commands**
   - When executing SQL files that may include `VACUUM` or other non-transaction commands, run them via `psql -f` flow instead of single-driver `execute()` batching that can wrap statements in one transaction.
   - If a Python path is required, split execution so utility commands run in standalone autocommit statements.

32. **Keep synthetic recency fields bounded to present time when used for seed ordering**
   - If workload seeding orders by recency fields (for example `updated_at DESC`), generation logic must not create future timestamps.
   - Cap generated recency timestamps at generation-time `now` to avoid biased seed-context concentration.

33. **Do not keep dead runtime knobs**
   - Any environment setting parsed into `Settings` (for example `BLOAT_ROUNDS`) must be consumed by execution scripts/SQL in the same behavior path.
   - If an env variable cannot be wired end-to-end, remove it from config/docs rather than leaving it silently ineffective.

34. **Use infrastructure names in publication-facing environment comparisons**
   - In performance and run-context docs, label environments by concrete platform/topology (for example `local Docker`, `AWS RDS server`) instead of org-role labels (for example `DBA environment`).
   - Keep wording consistent across section titles, tables, references, and changelog entries when this naming is updated.

### Section 3: Repository Constraints
Hard boundaries for this repository.

1. **Do not mix bloat logic with core query workloads**
   - Keep intentional bloat generation strict to `sql/006_bloat_workload.sql`
   - Do not add `UPDATE` loops or churn logic to `sql/004_queries_core.sql` or `src/poc/run_queries.py`
   - Ensures performance baselines remain uncontaminated by test-setup overhead

2. **Do not use relative paths for file operations**
   - Always resolve paths relative to the project root using `pathlib` or `os.path.abspath`
   - Do not rely on the current working directory being correct
   - Ensures scripts run reliably regardless of invocation location (e.g., from `scripts/` vs root)

3. **Do not document maintenance steps that scripts do not execute**
   - Do not claim a phase runs `VACUUM`/`VACUUM ANALYZE` unless that command is executed in repository scripts or SQL workflow files
   - If behavior differs by phase, document each phase explicitly (for example, post-load `ANALYZE` vs post-bloat `VACUUM ANALYZE`)
   - Prevents baseline interpretation errors in DBA review

4. **Do not store temporary analysis outside `docs/tmp/`**
   - Summaries, investigation notes, reviews, and drafts are temporary artifacts and must be created only under `docs/tmp/`
   - By task end, delete temporary artifacts or promote durable content into canonical docs

5. **Do not modify shared RFC command/example artifacts unless explicitly requested**
   - Do not edit `.opencode/command/create-design-rfc.md` or `docs/examples/design-rfc-*` by default when the task is about this repository's docs/performance outputs
   - Capture reusable lessons in this repository's active instruction files (`AGENTS.md`, `.opencode/command/learn.md`) unless the user asks for cross-project artifact updates

6. **Do not introduce scope creep in command specs**
   - Keep `.opencode/command/learn.md` focused on learning-workflow mechanics (lesson extraction, placement, consolidation, and qualification gates).
   - Do not add session-specific operational runbook/tuning rules there unless the user explicitly asks to expand that command's scope.

7. **Do not commit absolute local filesystem paths**
   - Do not include machine-local absolute paths (for example `/Users/...`, `C:\...`) in tracked docs, configs, or source files.
   - Use repository-relative paths or path-neutral wording in all tracked content.
