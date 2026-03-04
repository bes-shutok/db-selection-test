# Testing Algorithm and SQL Reference

## Core Concepts
- Baseline phase: query execution on freshly loaded data before intentional churn.
- Pre-bloat phase: script-run label for baseline execution in orchestrated runs.
- Post-bloat phase: query execution after intentional update churn and maintenance.
- Timing artifacts: `timings*.csv` and `timings_summary*.csv` files written per phase.
- Explain artifacts: `explain/*.txt` plans for complex queries.
- Baseline version: PostgreSQL `16.8` for consent behavior and performance validation.

## 1. Introduction
This document describes the testing algorithm used in the CRM PostgreSQL POC and provides a reference for the SQL schemas, indexes, and queries executed. It is intended for Database Administrators (DBAs) and performance engineers analyzing the results.

**Note:** Explain plans (EXPLAIN ANALYZE) are generated separately during execution and captured as run artifacts.

### 1.1 Baseline Version Scope
The workload and query contracts in this document are the canonical baseline for PostgreSQL `16.8` validation.

### 1.2 Context: PostgreSQL vs. MySQL (InnoDB)
This POC validates PostgreSQL as an alternative to a standard MySQL (InnoDB) stack. For DBAs familiar with MySQL, the following fundamental architectural differences drive the specific testing logic and tuning parameters used here:

| Feature | MySQL (InnoDB) | PostgreSQL (Heap) | POC Implication |
| :--- | :--- | :--- | :--- |
| **Primary Key** | **Clustered Index**: The table *is* the B-Tree of the PK. | **Heap**: The table is an unordered heap. PK is just another index pointing to the heap. | PK lookups in PG involve an index scan + heap fetch (unless Index-Only Scan). |
| **Secondary Indexes** | Point to the **Primary Key** value. | Point to the **Physical Location (CTID)** in the heap. | PG secondary index scans are faster (direct pointer) but require maintenance if the row moves (HOT updates mitigate this). |
| **MVCC (Updates)** | **Undo Logs**: Old versions kept in a separate area (Undo Tablespace). | **Multi-Version Tuples**: Old and new versions exist in the main table heap. | **Crucial**: Updates in PG create "dead tuples" in the main table that *must* be cleaned up. |
| **Garbage Collection** | **Purge Threads**: Background threads clean up undo logs. | **VACUUM**: Background process (Autovacuum) marks dead tuples for reuse. | The "Bloat" phase specifically tests `VACUUM` efficiency, which is the #1 operational difference from MySQL. |
| **JSON Storage** | **Native Binary JSON**: Stored inline or BLOB. Partial updates supported via `JSON_SET`. | **JSONB**: Decomposed binary format. **No Partial Update**: `jsonb_set` creates a full copy of the column value. | We strictly test JSONB update performance because modifying a single key rewrites the entire JSONB blob. |

---

## 2. Technical Architecture & Optimizations

This POC employs specific PostgreSQL features and tuning parameters to simulate a high-performance CRM environment.

### 2.1 Extensions

| Extension | Purpose | Justification |
| :--- | :--- | :--- |
| **`pgcrypto`** | Cryptographic functions | Enabled during schema setup for PostgreSQL feature parity and optional SQL-side experiments. Synthetic data generation in this POC is implemented in Python. |
| **`pg_stat_statements`** | Query statistics extension | Enabled during setup/cleanup when available. In load mode, phase-scoped snapshots can be reset/captured into run artifacts for DBA diagnostics. |

### 2.2 Storage Parameters & Autovacuum Tuning
Standard PostgreSQL defaults are often insufficient for tables with high update churn (like user profiles or session data). We explicitly tune these parameters:

> **Comparison to MySQL**:
> *   **InnoDB**: Uses `innodb_fill_factor` for *index leaf pages* only.
> *   **PostgreSQL**: `fillfactor` applies to the *heap table* pages. This is the **most critical tuning** for update-heavy tables in PG.

*   **`fillfactor`**:
    *   **`profile_properties` (75%)**: This JSONB table sees frequent updates (patches). A lower fillfactor leaves 25% free space per page, allowing **HOT (Heap Only Tuple)** updates.
        *   **HOT Benefit**: If the new tuple fits on the same page, PG creates a pointer chain and *skips updating all indexes*. This dramatically reduces write amplification compared to MySQL where secondary indexes point to the PK and might be unaffected, but the PK tree itself must be modified.
    *   **`consent` (85%)**: Moderate update volume. 15% free space balances storage density with update overhead.

*   **Autovacuum Scale Factors**:
    *   **`autovacuum_vacuum_scale_factor`**:
        *   **`profile_properties` (0.02)**: Triggers autovacuum when 2% of rows change. Defaults (20%) are too slow for large tables, leading to massive bloat spikes. Tighter thresholds keep table size and statistics stable.
        *   **`message_events` (0.05)**: Append-heavy. 5% is sufficient to clean up occasional deletes or updates without aggressive overhead.
    *   **`autovacuum_analyze_scale_factor` (0.01)**:
        *   Ensures the query planner has up-to-date statistics (histogram bounds, most common values) when just 1% of data changes. This is critical for JSONB queries where value distributions shift rapidly during updates.

### 2.3 Explicit Maintenance Operations
*   **Post-load `ANALYZE`**:
    *   **Usage**: Executed after bulk loading (Phase 1).
    *   **Why**: Bulk `COPY` operations do not trigger autoanalyze immediately, so we collect planner statistics before baseline reads.
*   **`VACUUM ANALYZE`**:
    *   **Usage**: Executed manually after the bloat workload (Phase 3).
    *   **Comparison to MySQL**: Equivalent to `OPTIMIZE TABLE` but runs concurrently without locking the table (in standard `VACUUM` mode).
    *   **Why**:
        *   **After Bloat**: We simulate a maintenance window. While autovacuum runs in the background, a manual vacuum ensures a known state (dead tuples marked for reuse) before the "Post-Bloat" measurement, isolating the effect of physical fragmentation (bloat) from simple dead tuple accumulation.

### 2.4 Indexing Strategy
The indexing strategy targets specific query patterns:

1.  **JSONB Containment (`@>`)**:
    *   **Index**: `gin (custom_properties jsonb_path_ops)`
    *   **Comparison to MySQL**: Roughly equivalent to Multi-Valued Indexes on JSON arrays, but GIN is a general-purpose inverted index supporting arbitrary key/value combinations without needing generated columns.
    *   **What is GIN?**: Generalized Inverted Index. Unlike a B-Tree which stores values in sorted order, GIN stores mappings of `value -> row_ids`. For JSONB, it indexes every key and value path, allowing instant lookups of "documents containing X" without scanning the table.
    *   **Why**: `jsonb_path_ops` is smaller and faster than the default `jsonb_ops` but only supports containment checks (`@>`). This is the primary pattern for segmenting users by attributes (e.g., `properties @> '{"vip": true}'`).

2.  **Partial Indexes**:
    *   **Index**: `WHERE channel = 'sms' AND purpose = 'marketing' AND state = 'opted_in'`
    *   **Why**: Drastically reduces index size and maintenance cost for the "hot path" (finding eligible users for campaigns), ignoring the long tail of opted-out or irrelevant records.

3.  **Extended Statistics (MCV)**:
    *   **Definition**: `CREATE STATISTICS ... (mcv) ON ...`
    *   **Why**: Standard statistics assume column independence. In CRM data, columns are often correlated (e.g., `country` and `language`). MCV (Multi-Column Frequent Value) lists help the planner estimate row counts accurately for queries like `WHERE country='NG' AND language='en'`, preventing poor join choices.

4.  **BRIN Indexes**:
    *   **Index**: `BRIN (event_time)` on `message_events`
    *   **Why**: For large, time-ordered append-only tables, Block Range Indexes (BRIN) are tiny compared to B-Trees and extremely efficient for range queries (e.g., "last 30 days").
    *   **Comparison to MySQL**: No direct equivalent in InnoDB. MySQL would typically use B-Trees (large size overhead) or Table Partitioning (pruning) to solve this. BRIN offers a lightweight alternative to partitioning for simple time-range filtering.

---

## 3. Data Examples

### 3.1 Profiles (Base Dimensions)
**Table**: `profiles`
Standard relational columns for rigid dimensions.

| tenant_id | profile_id | status | country | language |
| :--- | :--- | :--- | :--- | :--- |
| `260217...01` | `240219...001` | `ACTIVE` | `NG` (31%) | `en` (68%) |
| `260217...01` | `240219...002` | `ACTIVE` | `KE` (19%) | `sw` (8%) |
| `260217...01` | `240219...003` | `DELETED` | `GH` (14%) | `en` |

> **Variation**: Countries are skewed (NG 31%, KE 19%, GH 14%...). Languages follow (en 68%, fr 12%, sw 8%).

### 3.2 Profile Properties (JSONB)
**Table**: `profile_properties`
Stores flexible, tenant-defined attributes.

**Example A (High Value VIP):**
```json
{
  "plan": "vip",
  "vip": true,
  "vip_level": "gold",
  "segment": "high_value",
  "risk_band": "low",
  "deposit": {
    "bucket": "high",
    "last_at": "2024-02-15T10:00:00+00:00"
  },
  "tags": ["sportsbook", "high_value"]
}
```

**Example B (New User):**
```json
{
  "plan": "free",
  "vip": false,
  "segment": "new",
  "risk_band": "medium",
  "deposit": {
    "bucket": "low",
    "last_at": "2024-02-18T09:00:00+00:00"
  },
  "tags": ["casino"]
}
```

**Bloated State (After Workload):**
```json
{
  "plan": "vip",
  ...
  "churn_counter": 20,
  "bloat_round_ts": "2024-02-19T14:30:00+00:00",
  "last_patch_ts": "2024-02-19T14:30:00+00:00"
}
```

### 3.3 Consent
**Table**: `consent`
Tracks permission state per channel/purpose.

| profile | channel | purpose | state | updated_at |
| :--- | :--- | :--- | :--- | :--- |
| `...001` | `sms` | `marketing` | `opted_in` | `2024-02-19...` |
| `...001` | `email` | `transactional` | `opted_in` | `2024-02-19...` |
| `...002` | `push` | `marketing` | `opted_out` | `2024-02-18...` |

### 3.4 Message Events
**Table**: `message_events`
Append-only log of communications.

| event_id | channel | event_type | attributes (JSONB) |
| :--- | :--- | :--- | :--- |
| `1001` | `email` | `sent` | `{"provider": "sparkpost", "template_id": "tmpl_101", "region": "eu"}` |
| `1002` | `sms` | `delivered` | `{"provider": "twilio", "delivery_bucket": "priority"}` |
| `1003` | `push` | `opened` | `{"provider": "internal", "region": "af"}` |


---

## 4. Detailed Testing Algorithm

The testing process is automated to ensure reproducibility. Below is the step-by-step logic with actual data volumes for the **Baseline** scale.

### Phase 1: Setup & Seeding
1.  **Clean**: Drop existing tables to ensure a fresh state.
2.  **Schema**: Apply DDL with optimized storage parameters.
3.  **Generate**: deterministic generator creates CSVs with Random Seed `42`.
    *   **Volume (Baseline)**:
        *   `profiles`: **100,000** rows.
        *   `profile_properties`: **100,000** rows (1 per profile).
        *   `consent`: **900,000** rows (9 per profile: 3 channels × 3 purposes).
        *   `message_events`: **5,000,000** rows (append-only history).
    *   *Skew*: Uses weighted choices (e.g., 68% 'en', 12% 'fr') to mimic real demographics.
4.  **Load**: `COPY` commands bulk load data into PostgreSQL.
5.  **Analyze**: `ANALYZE` is run immediately to build initial statistics.
Concrete setup/seeding SQL examples and historical row evidence are listed in Section 5.1.

### Phase 2: Baseline Execution
We establish a performance baseline on the fresh, optimized database.
The focus here is capturing **query execution plans** and **latency distribution** in a stable state.

In two-phase bloat workflows this baseline stage is labeled `pre_bloat`.
Standalone execution can also be run as a single `baseline` phase.

> **Run Profiles**: `--profile iterations|load|both` (env default: `QUERY_RUN_PROFILE=both`).
> *   `iterations`: deterministic per-query latency percentiles.
> *   `load`: concurrent workers with phase throughput/QPS outputs.
> *   `both`: executes both in the same phase.
>
> **Note on Iterations**: The default `QUERY_ITERATIONS` is set to **10**.
> *   **Why so low?** This POC validates architectural behavior (Explain Plans, Index usage), not peak throughput. The "Complex" queries scan millions of rows; running them 1,000 times would make local execution prohibitively slow.
> *   **Stability**: 10 runs are sufficient to warm the buffer cache and capture a representative `EXPLAIN ANALYZE` output.
> *   **Configurable**: For true latency benchmarking (p99 stability), DBAs can increase this value via the `.env` file (e.g., `QUERY_ITERATIONS=1000`).

```python
# Execution logic
# 1. Resolve run profile:
# --profile iterations|load|both (default from QUERY_RUN_PROFILE)

# 2. Iteration mode (if selected):
#    Execute each named query QUERY_ITERATIONS times (single connection)
# --phase baseline   -> timings.csv, timings_summary.csv
# --phase pre_bloat  -> timings_pre_bloat.csv, timings_summary_pre_bloat.csv

# 3. Load mode (if selected):
#    - start LOAD_WORKERS concurrent connections
#    - warmup for LOAD_WARMUP_SECONDS
#    - record for LOAD_DURATION_SECONDS
#    - write load_executions*.csv, load_summary*.csv, load_phase_summary*.csv
#    - QPS = calls / measured phase duration seconds

# 4. pg_stat_statements (load mode):
#    - optional reset at phase start
#    - optional top-N capture at phase end
#    - writes pg_stat_statements*.csv and pg_stat_statements*_status.txt

# 5. EXPLAIN plans for complex queries (baseline/pre_bloat only)
#    capture plan text artifacts for each complex query.
```

### Phase 3: Bloat Injection
We simulate the degradation that happens after days/weeks of operation.
This phase runs strictly in SQL to maximize throughput and creates significant churn.

**Step 1: Property Churn**
*   **Target**: `profile_properties` (100k rows)
*   **Volume**: 20 loops × 20% of table ≈ **400,000 Updates**
*   **Effect**: Creates ~4 dead tuples for every live tuple on average, forcing aggressive HOT updates and page splits.
```sql
-- Executed in SQL
FOR i IN 1..20 LOOP
  UPDATE profile_properties 
  SET custom_properties = jsonb_set(..., 'churn_counter', i), ...
  WHERE random() < 0.20;
END LOOP;
```

**Step 2: Consent Flip-Flop**
*   **Target**: `consent` (900k rows total, ~300k 'marketing' rows)
*   **Volume**: 10 loops × 12% of 'marketing' rows ≈ **360,000 Updates**
*   **Effect**: Stresses the `consent` table and its indexes by flipping states.

**Step 3: Vacuum**
*   We run `VACUUM ANALYZE` manually at the end to clean up, but the physical file size and bloat (fragmentation) remain to be measured.

### Phase 4: Post-Bloat Measurement
We repeat the selected Phase 2 workload profile(s) to measure regression.

```python
# Execution logic for post-bloat phase

# Same profile behavior as Phase 2:
# - iterations -> timings_post_bloat.csv, timings_summary_post_bloat.csv
# - load -> load_executions_post_bloat.csv, load_summary_post_bloat.csv,
#           load_phase_summary_post_bloat.csv (+ optional pg_stat_statements_post_bloat.csv)
```

### Phase 5: Metric Collection
Finally, we query internal PostgreSQL statistics to quantify the damage.

1.  **Table Size & Bloat**: `pg_stat_user_tables` (n_dead_tup, table_size).
2.  **Index Size**: `pg_stat_user_indexes` (Compare index size vs table size).
3.  **TOAST Size**: Check if JSONB out-of-line storage has grown disproportionately.
4.  **Vacuum Health**: Check `last_autovacuum` timestamps to verify our tuning triggered correctly.

---

## 5. SQL Query Reference

### 5.1 DDL (Schema)

```sql
-- Profile Properties (JSONB-heavy, high update frequency)
CREATE TABLE IF NOT EXISTS profile_properties (
  tenant_id VARCHAR(45) NOT NULL,
  profile_id VARCHAR(45) NOT NULL,
  custom_properties JSONB NOT NULL,
  properties_version BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, profile_id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES profiles(tenant_id, profile_id)
) WITH (fillfactor = 75);

ALTER TABLE profile_properties
  SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_scale_factor = 0.01
  );
```

#### 5.1.1 Phase 1 Setup & Seeding SQL (Historical Run: `20260226_1608_w10`)

Bulk load SQL pattern used by loader (`COPY ... FROM STDIN`):

```sql
COPY profiles (tenant_id, profile_id, status, country, language, created_at, updated_at)
FROM STDIN WITH (FORMAT csv, HEADER true);

COPY profile_properties (tenant_id, profile_id, custom_properties, properties_version, updated_at)
FROM STDIN WITH (FORMAT csv, HEADER true);

COPY consent (tenant_id, profile_id, channel, purpose, state, updated_at, source)
FROM STDIN WITH (FORMAT csv, HEADER true);

COPY message_events (tenant_id, profile_id, campaign_id, channel, event_type, event_time, attributes)
FROM STDIN WITH (FORMAT csv, HEADER true);
```

Real CSV rows used by the `COPY` load in run `20260226_1608_w10`:
These are excerpts only (not full files): the run generated `100000` `profiles`, `100000` `profile_properties`, `900000` `consent`, and `5000000` `message_events` rows before static seed inserts.

`profiles.csv`
```csv
tenant_id,profile_id,status,country,language,created_at,updated_at
260217000000ups00000001,260226113105prf000000001,ACTIVE,NG,en,2025-05-16T11:06:32.940573+00:00,2025-06-11T11:06:32.940573+00:00
260217000000ups00000001,260226113105prf000000002,ACTIVE,NG,en,2026-02-14T21:47:17.940591+00:00,2026-03-09T21:47:17.940591+00:00
```

`profile_properties.csv`
```csv
tenant_id,profile_id,custom_properties,properties_version,updated_at
260217000000ups00000001,260226113105prf000000001,"{""plan"":""pro"",""vip"":false,""vip_level"":""bronze"",""segment"":""retention_push"",""deposit"":{""bucket"":""mid"",""last_at"":""2026-01-11T19:18:49.448319+00:00""},""risk_band"":""low"",""tags"":[""reactivation"",""casino"",""sportsbook""],""last_bet_at"":""2026-01-19T04:29:54.448342+00:00""}",4,2026-02-26T11:31:06.448364+00:00
```

`consent.csv`
```csv
tenant_id,profile_id,channel,purpose,state,updated_at,source
260217000000ups00000001,260226113105prf000000001,email,marketing,opted_in,2026-01-24T23:01:24.393564+00:00,import
260217000000ups00000001,260226113105prf000000001,email,transactional,opted_in,2025-11-12T18:47:31.393573+00:00,admin
```

`message_events.csv`
```csv
tenant_id,profile_id,campaign_id,channel,event_type,event_time,attributes
260217000000ups00000001,260226113105prf000008926,260226113109cmp000000154,sms,delivered,2026-02-06T18:44:00.770815+00:00,"{""provider"":""sparkpost"",""template_id"":""tmpl_160"",""delivery_bucket"":""normal"",""region"":""af""}"
260217000000ups00000001,260226113106prf000077396,260226113109cmp000000003,push,sent,2025-11-05T06:23:09.770848+00:00,"{""provider"":""sparkpost"",""template_id"":""tmpl_152"",""delivery_bucket"":""normal"",""region"":""af""}"
```

Static seed SQL applied after bulk load:

```sql
INSERT INTO profiles (tenant_id, profile_id, status, country, language, created_at, updated_at)
VALUES
  ('260217000000ups00000001', '260218120000000100000001', 'ACTIVE', 'NG', 'en', now() - interval '15 days', now()),
  ('260217000000ups00000001', '260218120000000100000002', 'ACTIVE', 'KE', 'en', now() - interval '13 days', now()),
  ('260217000000ups00000001', '260218120000000100000003', 'DELETED', 'GH', 'en', now() - interval '10 days', now())
ON CONFLICT DO NOTHING;
```

Historical volume evidence for this run:

| Table | CSV lines (`wc -l`) | Generated rows (minus header) | Static seed rows | Expected rows after Phase 1 |
| :--- | ---: | ---: | ---: | ---: |
| `profiles` | 100001 | 100000 | 3 | 100003 |
| `profile_properties` | 100001 | 100000 | 3 | 100003 |
| `consent` | 900001 | 900000 | 3 | 900003 |
| `message_events` | 5000001 | 5000000 | 3 | 5000003 |

The same run's pre-bloat metrics snapshot reports `n_live_tup` of `100003` (profiles), `100003` (profile_properties), `900003` (consent), and `5000220` (message_events). For `message_events`, `n_live_tup` comes from PostgreSQL statistics and can be approximate on large tables.

### 5.2 Core Read Queries

**`core_profile_lookup`**
```sql
SELECT p.profile_id,
       p.status,
       p.country,
       p.language,
       pp.custom_properties,
       pp.properties_version
FROM profiles p
JOIN profile_properties pp
  ON pp.tenant_id = p.tenant_id
 AND pp.profile_id = p.profile_id
WHERE p.tenant_id = %s
  AND p.profile_id = %s;
```

**`core_consent_lookup`**
```sql
SELECT c.profile_id,
       c.channel,
       c.purpose,
       c.state,
       c.updated_at
FROM consent c
WHERE c.tenant_id = %s
  AND c.profile_id = %s
  AND c.channel = %s
  AND c.purpose = %s;
```

**`core_segment_candidates`**
```sql
SELECT p.profile_id
FROM profiles p
JOIN profile_properties pp
  ON pp.tenant_id = p.tenant_id
 AND pp.profile_id = p.profile_id
JOIN consent c
  ON c.tenant_id = p.tenant_id
 AND c.profile_id = p.profile_id
WHERE p.tenant_id = %s
  AND p.status = 'ACTIVE'
  AND p.country = %s
  AND p.language = %s
  AND c.channel = %s
  AND c.purpose = %s
  AND c.state = %s
LIMIT %s;
```

### 5.3 Write Queries

**`write_patch_properties`**
```sql
UPDATE profile_properties
SET custom_properties = custom_properties || jsonb_build_object('plan', %s::text, 'last_patch_ts', now()::text),
    properties_version = properties_version + 1,
    updated_at = now()
WHERE tenant_id = %s
  AND profile_id = %s
  AND properties_version = %s
RETURNING
  NULL::bigint AS old_version,
  properties_version AS new_version,
  NULL::text AS old_plan,
  custom_properties ->> 'plan' AS new_plan;
```

**`write_upsert_consent`**
```sql
INSERT INTO consent (tenant_id, profile_id, channel, purpose, state, updated_at, source)
VALUES (%s, %s, %s, %s, %s, now(), %s)
ON CONFLICT (tenant_id, profile_id, channel, purpose)
DO UPDATE SET state = EXCLUDED.state,
              updated_at = EXCLUDED.updated_at,
              source = EXCLUDED.source
RETURNING
  NULL::text AS old_state,
  state AS new_state,
  updated_at AS new_updated_at;
```

### 5.4 Complex Analysis (OLAP-ish)

**`complex_jsonb_segmentation`**
```sql
SELECT p.country,
       p.language,
       COUNT(*) AS matched_profiles
FROM profiles p
JOIN profile_properties pp
  ON pp.tenant_id = p.tenant_id
 AND pp.profile_id = p.profile_id
JOIN consent c
  ON c.tenant_id = p.tenant_id
 AND c.profile_id = p.profile_id
WHERE p.tenant_id = %s
  AND p.status = 'ACTIVE'
  AND c.channel = 'sms'
  AND c.purpose = 'marketing'
  AND c.state = 'opted_in'
  AND pp.custom_properties @> '{"vip": true}'::jsonb
  AND pp.custom_properties @> ANY (
    ARRAY[
      '{"deposit":{"bucket":"high"}}'::jsonb,
      '{"deposit":{"bucket":"mid"}}'::jsonb
    ]
  )
  AND pp.custom_properties @> ANY (
    ARRAY[
      '{"risk_band":"low"}'::jsonb,
      '{"risk_band":"medium"}'::jsonb
    ]
  )
GROUP BY p.country, p.language
ORDER BY matched_profiles DESC
LIMIT 20;
```

**`complex_event_rollup`**
```sql
SELECT me.campaign_id,
       me.channel,
       DATE(me.event_time) AS event_day,
       COUNT(*) FILTER (WHERE me.event_type = 'sent') AS sent_count,
       COUNT(*) FILTER (WHERE me.event_type = 'delivered') AS delivered_count,
       COUNT(*) FILTER (WHERE me.event_type = 'failed') AS failed_count
FROM message_events me
WHERE me.tenant_id = %s
  AND me.event_time >= now() - interval '30 days'
GROUP BY me.campaign_id, me.channel, DATE(me.event_time)
ORDER BY event_day DESC, campaign_id
LIMIT 200;
```

**`complex_join_filter`**
```sql
WITH ranked AS (
  SELECT p.profile_id,
         p.country,
         p.language,
         pp.custom_properties,
         c.state AS marketing_sms_state,
         MAX(me.event_time) AS last_event_time,
         COUNT(*) FILTER (WHERE me.event_type = 'delivered') AS delivered_30d,
         ROW_NUMBER() OVER (
           PARTITION BY p.country
           ORDER BY COUNT(*) FILTER (WHERE me.event_type = 'delivered') DESC
         ) AS country_rank
  FROM profiles p
  JOIN profile_properties pp
    ON pp.tenant_id = p.tenant_id
   AND pp.profile_id = p.profile_id
  JOIN consent c
    ON c.tenant_id = p.tenant_id
   AND c.profile_id = p.profile_id
   AND c.channel = 'sms'
   AND c.purpose = 'marketing'
  JOIN message_events me
    ON me.tenant_id = p.tenant_id
   AND me.profile_id = p.profile_id
  WHERE p.tenant_id = %s
    AND p.status = 'ACTIVE'
    AND me.event_time >= now() - interval '30 days'
    AND pp.custom_properties @> ANY (
      ARRAY[
        '{"segment":"high_value"}'::jsonb,
        '{"segment":"retention_push"}'::jsonb,
        '{"segment":"reactivation"}'::jsonb
      ]
    )
    AND pp.custom_properties @> ANY (
      ARRAY[
        '{"plan":"pro"}'::jsonb,
        '{"plan":"vip"}'::jsonb
      ]
    )
  GROUP BY p.profile_id, p.country, p.language, pp.custom_properties, c.state
)
SELECT *
FROM ranked
WHERE country_rank <= 50
  AND marketing_sms_state = 'opted_in'
ORDER BY delivered_30d DESC
LIMIT 500;
```
