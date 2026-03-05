-- Bloat and table health metrics collection
-- Run after bloat workload to measure dead tuples, table sizes, and index bloat

-- Table bloat metrics
SELECT 
    schemaname,
    relname AS tablename,
    pg_size_pretty(pg_total_relation_size((quote_ident(schemaname)||'.'||quote_ident(relname))::regclass)) AS total_size,
    pg_size_pretty(pg_relation_size((quote_ident(schemaname)||'.'||quote_ident(relname))::regclass)) AS table_size,
    pg_size_pretty(pg_indexes_size((quote_ident(schemaname)||'.'||quote_ident(relname))::regclass)) AS indexes_size,
    n_live_tup,
    n_dead_tup,
    ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_tup_pct,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = current_schema()
ORDER BY n_dead_tup DESC;

-- Index bloat and usage
SELECT 
    schemaname,
    relname AS tablename,
    indexrelname AS indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = current_schema()
ORDER BY pg_relation_size(indexrelid) DESC;

-- TOAST table sizes (important for JSONB bloat)
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name,
    t.relname AS toast_table_name,
    pg_size_pretty(pg_total_relation_size(t.oid)) AS toast_size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class t ON t.oid = c.reltoastrelid
WHERE n.nspname = current_schema()
  AND c.relkind = 'r'
  AND t.oid IS NOT NULL
ORDER BY pg_total_relation_size(t.oid) DESC;

-- Autovacuum thresholds vs actual dead tuples
-- Derives threshold and scale_factor from pg_settings and table-level reloptions
WITH global_settings AS (
    SELECT 
        COALESCE(current_setting('autovacuum_vacuum_threshold', true)::bigint, 50) AS global_threshold,
        COALESCE(current_setting('autovacuum_vacuum_scale_factor', true)::real, 0.2) AS global_scale_factor
),
table_settings AS (
    SELECT 
        c.oid,
        n.nspname AS schemaname,
        c.relname,
        -- Extract table-level autovacuum_vacuum_threshold from reloptions if set
        CASE 
            WHEN c.reloptions IS NOT NULL THEN
                (SELECT option_value::bigint 
                 FROM unnest(c.reloptions) AS opt(option)
                 CROSS JOIN LATERAL (SELECT split_part(opt.option, '=', 1) AS option_name, split_part(opt.option, '=', 2) AS option_value) AS parsed
                 WHERE parsed.option_name = 'autovacuum_vacuum_threshold'
                 LIMIT 1)
            ELSE NULL
        END AS table_threshold,
        -- Extract table-level autovacuum_vacuum_scale_factor from reloptions if set
        CASE 
            WHEN c.reloptions IS NOT NULL THEN
                (SELECT option_value::real 
                 FROM unnest(c.reloptions) AS opt(option)
                 CROSS JOIN LATERAL (SELECT split_part(opt.option, '=', 1) AS option_name, split_part(opt.option, '=', 2) AS option_value) AS parsed
                 WHERE parsed.option_name = 'autovacuum_vacuum_scale_factor'
                 LIMIT 1)
            ELSE NULL
        END AS table_scale_factor
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema() AND c.relkind = 'r'
)
SELECT 
    s.schemaname,
    s.relname AS tablename,
    s.n_live_tup,
    s.n_dead_tup,
    -- autovacuum triggers when: dead_tuples > threshold + scale_factor * live_tuples
    -- Use table-level setting if defined, otherwise fall back to global setting
    COALESCE(ts.table_threshold, gs.global_threshold) AS threshold,
    COALESCE(ts.table_scale_factor, gs.global_scale_factor) AS scale_factor,
    COALESCE(ts.table_threshold, gs.global_threshold) + (COALESCE(ts.table_scale_factor, gs.global_scale_factor) * s.n_live_tup) AS autovacuum_threshold,
    CASE 
        WHEN s.n_dead_tup > (COALESCE(ts.table_threshold, gs.global_threshold) + COALESCE(ts.table_scale_factor, gs.global_scale_factor) * s.n_live_tup) 
        THEN 'SHOULD VACUUM'
        ELSE 'OK'
    END AS vacuum_status,
    s.last_autovacuum
FROM pg_stat_user_tables s
CROSS JOIN global_settings gs
LEFT JOIN table_settings ts ON ts.schemaname = s.schemaname AND ts.relname = s.relname
WHERE s.schemaname = current_schema()
ORDER BY s.relname;
