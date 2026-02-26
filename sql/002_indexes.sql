CREATE INDEX IF NOT EXISTS idx_profiles_status_country_lang
  ON profiles(tenant_id, status, country, language);

-- Path-ops GIN is smaller/faster for containment (@>) predicates that dominate
-- segmentation-style JSONB filters in this POC.
CREATE INDEX IF NOT EXISTS idx_profile_properties_gin_path_ops
  ON profile_properties USING GIN (custom_properties jsonb_path_ops);

-- Keep a direct expression index for common equality filters on plan.
CREATE INDEX IF NOT EXISTS idx_profile_properties_plan_expr
  ON profile_properties ((custom_properties ->> 'plan'));

CREATE INDEX IF NOT EXISTS idx_consent_state
  ON consent(tenant_id, channel, purpose, state);

CREATE INDEX IF NOT EXISTS idx_consent_marketing_optin_partial
  ON consent(tenant_id, profile_id)
  WHERE channel = 'sms' AND purpose = 'marketing' AND state = 'opted_in';

CREATE INDEX IF NOT EXISTS idx_message_events_tenant_time
  ON message_events(tenant_id, event_time);

CREATE INDEX IF NOT EXISTS idx_message_events_tenant_campaign_time
  ON message_events(tenant_id, campaign_id, event_time);

CREATE INDEX IF NOT EXISTS idx_message_events_tenant_profile_time
  ON message_events(tenant_id, profile_id, event_time);

-- BRIN complements btree indexes on large append-heavy time series scans.
CREATE INDEX IF NOT EXISTS idx_message_events_event_time_brin
  ON message_events USING BRIN (event_time) WITH (pages_per_range = 64);

-- Extended stats improve selectivity estimates for multi-column predicates.
CREATE STATISTICS IF NOT EXISTS st_profiles_filter_mcv (mcv)
  ON tenant_id, status, country, language FROM profiles;

CREATE STATISTICS IF NOT EXISTS st_consent_filter_mcv (mcv)
  ON tenant_id, channel, purpose, state FROM consent;

CREATE STATISTICS IF NOT EXISTS st_message_events_filter_mcv (mcv)
  ON tenant_id, channel, event_type FROM message_events;
