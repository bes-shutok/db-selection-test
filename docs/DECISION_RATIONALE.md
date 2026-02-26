# Core Concepts
- Decision record: a concrete choice made for this POC, including rationale and implications.
- Assumption: a temporary default used until an explicit external decision is provided.
- Non-goal: a deliberately excluded area to keep the POC focused.
- Revisit trigger: a condition that should force a decision review.

## 1. Purpose
This document explains why each major POC choice was made, so implementation and review can continue without re-opening settled decisions.

## 2. Decision Summary

| ID | Decision | Status | Owner Input |
|---|---|---|---|
| D1 | Use a standalone testing project (`db-selection-test`) | Accepted | CRM engineering |
| D2 | Keep POC lean (not MVP-complete) | Accepted | CRM engineering + DBA alignment |
| D3 | Model 4 tables only (`profiles`, `profile_properties`, `consent`, `message_events`) | Accepted | CRM engineering |
| D4 | Use synthetic data only | Accepted | DBA confirmed acceptable |
| D5 | Baseline/stretch sizes: `100k+5M`, `500k+20M` | Accepted (default) | Proposed by CRM, accepted by DBA |
| D6 | Workload pack: 3 reads, 2 writes, 3 complex queries | Accepted | DBA confirmed enough for validation |
| D7 | Intentional bloat testing required | Accepted | DBA requested update churn/bloat |
| D8 | Bloat targets: primary `profile_properties`, secondary `consent`, none on `message_events` | Accepted | CRM engineering rationale |
| D9 | Local Docker first, then DBA infra replay | Accepted | DBA confirmed |
| D10 | Python + `uv` for generator/runner tooling | Accepted | CRM engineering |
| D11 | Final pass/fail thresholds (p95/p99, CPU/memory) are DBA-owned | Open input required | DBA |

## 3. Rationale by Decision
### D1. Standalone sibling project
Reasoning:
- Keeps documentation/RFC workspace clean.
- Allows independent iteration speed for schema/data/query experiments.
- Low coupling to production service repos.

Tradeoff:
- Separate repo means explicit sync discipline is needed for future contract changes.

### D2 + D3. Lean scope with 4 tables
Reasoning:
- Objective is DB behavior validation, not service completeness.
- These tables are sufficient to represent key CRM query shapes:
  - profile dimensions
  - JSONB dynamic attributes
  - consent state
  - event rollups

Tradeoff:
- Not all CRM entities are modeled; some cross-service edge cases are intentionally excluded.

### D4. Synthetic data only
Reasoning:
- Faster generation and repeatability.
- No PII concerns.
- Easy scale tuning (baseline/stretch).

Tradeoff:
- May miss some real-world anomalies unless distributions are tuned iteratively.

### D5. Data scale defaults
Reasoning:
- Baseline (`100k + 5M`) gives quick iteration loop.
- Stretch (`500k + 20M`) gives meaningful scale signal for planner/index behavior.
- Suitable for engineering-side preparation before DBA deep stress runs.

Tradeoff:
- Larger tiers (for example `1M+`) remain possible if DBA asks for stronger signal.

### D6. Query pack size
Reasoning:
- Minimal set that still covers read/write/complex patterns.
- Keeps execution time practical.
- Provides enough artifacts for plan and latency review.

Tradeoff:
- Query diversity is limited; follow-up packs can be added if DBA requests.

### D7 + D8. Intentional bloat strategy
Reasoning:
- DBA explicitly asked for update churn to create bloat on purpose.
- `profile_properties` is the best primary target because JSONB update churn stresses MVCC/TOAST/index behavior.
- `consent` adds realistic update churn for operational writes.
- `message_events` is append-heavy by nature, so forced update bloat there would be less realistic.

Tradeoff:
- Bloat behavior in short local runs is limited; deeper observation expected on DBA infra.

### D9. Local then DBA infra
Reasoning:
- Local run validates correctness and repeatability.
- DBA infra is the authoritative environment for deeper performance interpretation.

Tradeoff:
- Local numbers are informative but not final pass/fail criteria.

### D10. Python + uv
Reasoning:
- Fastest path for synthetic data generation and script-based orchestration.
- Good ecosystem for distributions, generation, and DB interaction.
- `uv` gives reproducible environment and dependency flow.

Tradeoff:
- Not aligned with JVM production stack by default; acceptable because this is a DB-focused POC.

### D11. DBA-owned thresholds
Reasoning:
- Infrastructure and acceptance interpretation are owned by DBA.
- Engineering provides artifacts and measured results.

Current gap:
- Explicit thresholds by query group (p95/p99) and resource criteria are pending DBA confirmation.

## 4. Non-Goals (Explicit)
1. Implementing full CRM service APIs.
2. Modeling all six CRM service schemas.
3. Replacing analytics warehouse behavior.
4. Establishing production SLOs from local-only runs.

## 5. Risks and Mitigations
1. Risk: Synthetic distributions are too clean.
- Mitigation: iterate distributions and add skew/outliers after first DBA review.

2. Risk: Plan changes across scale are misinterpreted.
- Mitigation: capture `EXPLAIN (ANALYZE, BUFFERS)` for complex queries and document explainable causes.

3. Risk: Scope creep turns POC into MVP.
- Mitigation: enforce lean scope and add scenarios only when tied to validation signal.

4. Risk: Missing threshold clarity blocks conclusion.
- Mitigation: treat thresholds as explicit DBA decision checkpoint before final verdict.

## 6. Revisit Triggers
Re-open decisions only if one of these occurs:
1. DBA requests additional schema/query classes.
2. Baseline/stretch runs show insufficient signal.
3. Unexpected planner/path regressions require broader table modeling.
4. CRM product scope changes require new operational predicates.
