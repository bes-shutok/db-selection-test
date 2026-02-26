# Core Concepts
- Engine-level optimization: improvements provided by PostgreSQL runtime/planner itself.
- Schema/query-level optimization: choices we control in DDL/DML (indexes, predicates, maintenance settings).
- Containment predicate: JSONB filter using `@>`.

## Purpose
This note summarizes the optimization posture used by the PostgreSQL `16.8` baseline in this POC.
It is focused on practical schema/query choices that DBAs can reproduce directly.

## 1. What we are explicitly doing in SQL
1. JSONB containment-friendly indexing
- `GIN (custom_properties jsonb_path_ops)` for heavy `@>` predicates.
- Query filters use `@> ...` with `ANY (ARRAY[...])` for readability while preserving containment semantics.

2. Mixed index strategy for event workloads
- btree indexes for selective tenant/campaign/profile lookups.
- BRIN on `event_time` for broad time-window scans on large append-heavy event tables.

3. Update-heavy table tuning
- lower `fillfactor` on `profile_properties` and `consent` to reduce page splits under churn.
- per-table autovacuum/analyze thresholds tuned tighter than defaults.

4. Better selectivity estimation
- `CREATE STATISTICS ... (mcv)` on common multi-column filter combinations.

5. DML observability under churn
- write queries use plain `RETURNING` target-table columns for lightweight result checks.

## 2. Baseline Engine Expectations (PostgreSQL 16.8)
1. Planner quality depends heavily on statistics quality.
- extended statistics (`MCV`) are required for correlated predicates.
- immediate `ANALYZE` after bulk load avoids unstable initial plans.

2. JSONB-heavy queries need explicit containment-friendly access paths.
- `jsonb_path_ops` GIN is preferred for `@>` containment patterns.
- query predicates should remain containment-based where possible.

3. Update churn must be controlled by table-level storage + vacuum settings.
- lower `fillfactor` reduces page split pressure.
- tighter table-level autovacuum thresholds reduce dead tuple buildup.

Important:
- most engine behavior is automatic, but predictable performance depends on correct schema/query design.

## 3. Why not convert all JSON keys to physical columns now
- This POC intentionally tests JSONB-heavy behavior.
- If specific keys become permanent high-frequency filters, promoting them to typed columns is a valid next optimization.
- Current compromise keeps flexibility while indexing critical paths.

## 4. Validation guidance
For each complex query, compare before/after at baseline and stretch scales using:
1. `EXPLAIN (ANALYZE, BUFFERS)`
2. p95/p99 latency
3. plan stability notes (changes acceptable when explainable and performance remains stable)

## References
- PostgreSQL release notes (16): https://www.postgresql.org/docs/16/release-16.html
- PostgreSQL JSON types/operators: https://www.postgresql.org/docs/16/datatype-json.html
- PostgreSQL GIN indexes: https://www.postgresql.org/docs/16/gin.html
- PostgreSQL BRIN indexes: https://www.postgresql.org/docs/16/brin.html
- PostgreSQL `RETURNING` clause: https://www.postgresql.org/docs/16/dml-returning.html
