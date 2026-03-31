-- Drop all tables in reverse dependency order
-- This ensures a clean slate for each POC run

DROP TABLE IF EXISTS message_events CASCADE;
DROP TABLE IF EXISTS consent CASCADE;
DROP TABLE IF EXISTS profile_properties CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;

-- Drop extended statistics objects (not automatically dropped with CASCADE)
DROP STATISTICS IF EXISTS st_profiles_filter_mcv;
DROP STATISTICS IF EXISTS st_consent_filter_mcv;
DROP STATISTICS IF EXISTS st_message_events_filter_mcv;

-- Reset pg_stat_statements to clear query history (conditional on extension existence)
DO $$
DECLARE
    pgstat_schema TEXT;
    reset_arity INTEGER;
BEGIN
    SELECT n.nspname, max(p.pronargs)
      INTO pgstat_schema, reset_arity
      FROM pg_extension e
      JOIN pg_namespace n
        ON n.oid = e.extnamespace
      LEFT JOIN pg_proc p
        ON p.pronamespace = e.extnamespace
       AND p.proname = 'pg_stat_statements_reset'
     WHERE e.extname = 'pg_stat_statements'
     GROUP BY n.nspname;

    IF pgstat_schema IS NULL THEN
        RETURN;
    END IF;

    IF reset_arity = 4 THEN
        EXECUTE format(
            'SELECT %I.pg_stat_statements_reset(0::oid, 0::oid, 0::bigint, false)',
            pgstat_schema
        );
    ELSIF reset_arity = 3 THEN
        EXECUTE format(
            'SELECT %I.pg_stat_statements_reset(0::oid, 0::oid, 0::bigint)',
            pgstat_schema
        );
    ELSIF reset_arity = 0 THEN
        EXECUTE format(
            'SELECT %I.pg_stat_statements_reset()',
            pgstat_schema
        );
    END IF;
END $$;
