# Core Concepts
- Communication log: concise record of stakeholder exchanges that shaped this POC.
- Alignment point: statement accepted by both CRM engineering and DBA.
- Open item: unresolved input still required for final acceptance.

## 1. Purpose
This log preserves the key communication context behind POC scope decisions, so contributors understand why choices were made.

## 2. Stakeholders
- CRM engineering representatives
- DBA representatives

## 3. Context from exchange
### 3.1 CRM side position
- PostgreSQL is not intended as long-term pure OLAP system.
- OLAP-ish behavior will still exist in operational CRM (segmentation, basic aggregations).
- Team asked what inputs DBA needs to make POC meaningful.

### 3.2 DBA side response
DBA requested CRM team to:
1. set up schema,
2. prepare representative dataset,
3. run sample queries,
and stated DBA can provide infra for load execution.

## 4. Clarification round and outcomes
### 4.1 Questions asked by CRM side
1. Target dataset size?
2. Is workload set sufficient (key reads/writes + complex queries)?
3. What success criteria?
4. What output artifacts are expected?
5. Is local Docker preparation acceptable before infra runs?

### 4.2 Responses from DBA side
1. Dataset proposal looked good; DBA additionally requested update churn to create bloat intentionally.
2. Workload set looked sufficient; DBA expected dynamic JSONB coverage.
3. DBA mentioned using CPU and p99 perspective and memory behavior observations for complex queries.
4. DBA emphasized evaluating `EXPLAIN (ANALYZE, BUFFERS)` and plan consistency under growth/writes.
5. Local Docker approach accepted, with note that strong bloat behavior is less visible in short-lived local runs.

## 5. Resulting alignment used in this project
1. Lean POC scope is accepted.
2. Synthetic data is accepted.
3. JSONB-heavy dynamic predicates are required.
4. Intentional bloat step is required.
5. Local-first then DBA-infra replay is accepted.
6. Explain plans are mandatory output artifacts.

## 6. Open items remaining
1. Exact pass/fail thresholds by query group (p95/p99).
2. Concrete CPU/memory threshold interpretation for final acceptance.

## 7. Working assumptions (until open items are resolved)
1. Baseline/stretch sizes: `100k+5M` and `500k+20M`.
2. Minor explainable plan changes are acceptable if performance remains stable.
3. Engineering delivers reproducible scripts/data/artifacts; DBA leads deeper stress interpretation.

## 8. Handoff expectation
Engineering handoff to DBA should include:
1. schema and index scripts,
2. synthetic data generation and load scripts,
3. query workload scripts,
4. explain plans and timing summaries,
5. run metadata and concise findings.

## 9. Document Correlation
1. Assumptions snapshots are used for early stakeholder/DBA alignment.
2. The standalone POC spec, CRM POC Specification (`CRM_POC_SPEC.md`), is the implementation source of truth once execution starts.
3. If either document changes, sync key scope/version assumptions in both to avoid drift during infra provisioning.
