-- name: complex_jsonb_segmentation
-- Baseline catalog uses @> + ANY(array) so jsonb_path_ops GIN can serve
-- multi-value containment filters with a single index path.
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

-- name: complex_event_rollup
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

-- name: complex_join_filter
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
