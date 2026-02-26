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
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
    ) THEN
        PERFORM pg_stat_statements_reset();
    END IF;
END $$;
