-- name: core_profile_lookup
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

-- name: core_consent_lookup
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

-- name: core_segment_candidates
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

-- name: write_patch_properties
-- 18.x comparison catalog: uses OLD/NEW aliases in RETURNING.
-- Automated runner still consumes `new_version` only; old/new deltas here are
-- primarily for richer manual observability.
UPDATE profile_properties
SET custom_properties = custom_properties || jsonb_build_object('plan', %s::text, 'last_patch_ts', now()::text),
    properties_version = properties_version + 1,
    updated_at = now()
WHERE tenant_id = %s
  AND profile_id = %s
  AND properties_version = %s
RETURNING
  OLD.properties_version AS old_version,
  NEW.properties_version AS new_version,
  OLD.custom_properties ->> 'plan' AS old_plan,
  NEW.custom_properties ->> 'plan' AS new_plan;

-- name: write_upsert_consent
-- 18.x comparison catalog: uses OLD/NEW aliases in RETURNING.
-- Returned state transitions are for observability; runner logic does not
-- depend on these values.
INSERT INTO consent (tenant_id, profile_id, channel, purpose, state, updated_at, source)
VALUES (%s, %s, %s, %s, %s, now(), %s)
ON CONFLICT (tenant_id, profile_id, channel, purpose)
DO UPDATE SET state = EXCLUDED.state,
              updated_at = EXCLUDED.updated_at,
              source = EXCLUDED.source
RETURNING
  COALESCE(OLD.state, 'inserted') AS old_state,
  NEW.state AS new_state,
  NEW.updated_at AS new_updated_at;
