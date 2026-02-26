CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE TABLE IF NOT EXISTS profiles (
  tenant_id VARCHAR(45) NOT NULL,
  profile_id VARCHAR(45) NOT NULL,
  status VARCHAR(16) NOT NULL,
  country CHAR(2) NULL,
  language VARCHAR(16) NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, profile_id)
);

CREATE TABLE IF NOT EXISTS profile_properties (
  tenant_id VARCHAR(45) NOT NULL,
  profile_id VARCHAR(45) NOT NULL,
  custom_properties JSONB NOT NULL,
  properties_version BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, profile_id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES profiles(tenant_id, profile_id)
) WITH (fillfactor = 75);

CREATE TABLE IF NOT EXISTS consent (
  tenant_id VARCHAR(45) NOT NULL,
  profile_id VARCHAR(45) NOT NULL,
  channel VARCHAR(16) NOT NULL,
  purpose VARCHAR(32) NOT NULL,
  state VARCHAR(16) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  source VARCHAR(32) NOT NULL,
  PRIMARY KEY (tenant_id, profile_id, channel, purpose),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES profiles(tenant_id, profile_id)
) WITH (fillfactor = 85);

CREATE TABLE IF NOT EXISTS message_events (
  tenant_id VARCHAR(45) NOT NULL,
  event_id BIGINT GENERATED ALWAYS AS IDENTITY,
  profile_id VARCHAR(45) NOT NULL,
  campaign_id VARCHAR(45) NOT NULL,
  channel VARCHAR(16) NOT NULL,
  event_type VARCHAR(16) NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  attributes JSONB NOT NULL,
  PRIMARY KEY (event_id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES profiles(tenant_id, profile_id)
);

ALTER TABLE profile_properties
  -- JSONB-heavy table with frequent updates: reserve page space and
  -- vacuum/analyze sooner to keep dead tuples and stats drift under control.
  SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_scale_factor = 0.01
  );

ALTER TABLE consent
  -- Operational churn table: slightly less aggressive than JSONB properties
  -- but still tighter than defaults for predictable write/query behavior.
  SET (
    autovacuum_vacuum_scale_factor = 0.03,
    autovacuum_analyze_scale_factor = 0.01
  );

ALTER TABLE message_events
  -- Append-heavy event table: tune for large volume while avoiding noisy
  -- analyze cadence from default thresholds at higher row counts.
  SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
  );
