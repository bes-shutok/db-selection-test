# Project Guidelines

## Core Concepts
- Comparison table reference: a per-row pointer to the exact result artifact or summary that supplied the table values.
- End-to-end environment comparison: a benchmark comparison where runner hardware, network path, and database topology can all influence the observed result.
- Sanitized infrastructure detail: non-secret capacity or topology facts kept without internal hostnames, endpoints, credentials, or connection strings.

## Repository-Specific Documentation Rules

1. **Cite source artifacts directly in comparison tables**
   - When a publication-facing doc compares runs or environments in a metrics table, include a per-row reference column that points to the exact result summary or canonical artifact used for that row.
   - Keep the reference aligned with the run ID shown in the same row so reviewers can trace each number back to its source without searching elsewhere in the document.

2. **State runner-capacity asymmetry in end-to-end environment comparisons**
   - When compared environments use materially different runner hardware, document the relevant runner capacity facts near the comparison and explicitly qualify the result as end-to-end rather than database-only.
   - Do not attribute throughput or latency gaps to the database tier alone unless runner capacity and access path are comparable or the document shows direct evidence isolating the DB as the cause.

3. **Keep shared docs free of sensitive infrastructure identifiers**
   - In publication-facing or shared repository docs, keep only sanitized infrastructure details such as generic platform labels and non-secret capacity facts.
   - Do not store internal hostnames, private service URLs, connection strings, usernames, passwords, tokens, or similarly sensitive infrastructure identifiers in tracked docs.

4. **Preserve quoted `psql` variable semantics in the Python SQL runner**
   - When SQL catalog execution is routed through `poc.sql_runner`, support both bare `:VAR` placeholders and quoted `:'VAR'` placeholders already used by repository SQL files.
   - Treat `:'VAR'` as SQL string-literal substitution and verify compatibility with an end-to-end script smoke test, not only unit tests.
