-- Intentional bloat workload.
-- Primary focus: profile_properties. Secondary focus: consent.

DO $$
DECLARE
  i INTEGER;
BEGIN
  FOR i IN 1..20 LOOP
    UPDATE profile_properties
    SET custom_properties = jsonb_set(
          custom_properties,
          '{churn_counter}',
          to_jsonb(i),
          true
        ) || jsonb_build_object('bloat_round_ts', now()::text),
        properties_version = properties_version + 1,
        updated_at = now()
    WHERE random() < 0.20;
  END LOOP;
END $$;

DO $$
DECLARE
  j INTEGER;
BEGIN
  FOR j IN 1..10 LOOP
    UPDATE consent
    SET state = CASE WHEN state = 'opted_in' THEN 'opted_out' ELSE 'opted_in' END,
        updated_at = now(),
        source = 'bloat_workload'
    WHERE purpose = 'marketing'
      AND random() < 0.12;
  END LOOP;
END $$;

VACUUM (ANALYZE) profile_properties;
VACUUM (ANALYZE) consent;
