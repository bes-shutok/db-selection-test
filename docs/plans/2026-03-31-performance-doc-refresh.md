# Plan: Performance Doc Refresh

## Context
Refresh the publication-facing performance analysis to incorporate the new AWS-premise PostgreSQL 16.8 runs (`20260331_102001`, `20260331_104205`, `20260331_110246`) and compare three execution paths: local Docker, local client to AWS RDS, and AWS client to AWS RDS. The update must stay evidence-first, cite every run used, and make clear where the local-to-RDS matrix is complete (`3`, `10`, `50`) versus where older text only described partial coverage.

## Validation Commands
```bash
sed -n '1,260p' docs/PERFORMANCE_ANALYSIS_POSTGRESQL_VS_MYSQL.md
rg -n "20260331_102001|20260331_104205|20260331_110246|20260330_194724|20260305_155121|20260305_161908|20260226_1608_w03b|20260226_1608_w10b|20260226_1608_w50" docs/PERFORMANCE_ANALYSIS_POSTGRESQL_VS_MYSQL.md
```

### Task 1: Consolidate Comparison Inputs
Files:
- `docs/PERFORMANCE_ANALYSIS_POSTGRESQL_VS_MYSQL.md`

- [ ] Replace the old executive-summary environment bullets so they reflect the three comparison conditions and the new AWS-premise run IDs.
- [ ] Update the run-context section to document the AWS-premise `3/10/50` matrix and the local-to-RDS `3/10/50` evidence used for comparison.
- [ ] Remove or rewrite statements that still describe the remote RDS comparison as only `3` and `10` workers when newer evidence exists.

### Task 2: Refactor Comparison Sections
Files:
- `docs/PERFORMANCE_ANALYSIS_POSTGRESQL_VS_MYSQL.md`

- [ ] Add a clear three-condition comparison section for local Docker vs local-to-RDS vs AWS-to-AWS RDS with phase-level throughput evidence.
- [ ] Refresh worker-scaling tables so `3`, `10`, and `50` workers are compared consistently across the environments that now have data.
- [ ] Update supporting narrative to separate network-path effects from database-capacity observations and to call out any remaining comparability limits.

### Task 3: Refresh Evidence References
Files:
- `docs/PERFORMANCE_ANALYSIS_POSTGRESQL_VS_MYSQL.md`

- [ ] Update run IDs, artifact references, and source listings to include every run actually cited in the comparison.
- [ ] Re-check document text for stale conclusions that conflict with the new AWS-premise results.
