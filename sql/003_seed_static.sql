INSERT INTO profiles (tenant_id, profile_id, status, country, language, created_at, updated_at)
VALUES
  ('260217000000ups00000001', '260218120000000100000001', 'ACTIVE', 'NG', 'en', now() - interval '15 days', now()),
  ('260217000000ups00000001', '260218120000000100000002', 'ACTIVE', 'KE', 'en', now() - interval '13 days', now()),
  ('260217000000ups00000001', '260218120000000100000003', 'DELETED', 'GH', 'en', now() - interval '10 days', now())
ON CONFLICT DO NOTHING;

INSERT INTO profile_properties (tenant_id, profile_id, custom_properties, properties_version, updated_at)
VALUES
  ('260217000000ups00000001', '260218120000000100000001', '{"plan":"pro","vip_level":"gold","segment":"high_value","deposit":{"bucket":"high"}}'::jsonb, 1, now()),
  ('260217000000ups00000001', '260218120000000100000002', '{"plan":"free","vip_level":"silver","segment":"reactivation","deposit":{"bucket":"mid"}}'::jsonb, 1, now()),
  ('260217000000ups00000001', '260218120000000100000003', '{"plan":"free","vip_level":"bronze","segment":"inactive","deposit":{"bucket":"low"}}'::jsonb, 1, now())
ON CONFLICT DO NOTHING;

INSERT INTO consent (tenant_id, profile_id, channel, purpose, state, updated_at, source)
VALUES
  ('260217000000ups00000001', '260218120000000100000001', 'sms', 'marketing', 'opted_in', now(), 'seed'),
  ('260217000000ups00000001', '260218120000000100000002', 'sms', 'marketing', 'opted_out', now(), 'seed'),
  ('260217000000ups00000001', '260218120000000100000001', 'email', 'transactional', 'opted_in', now(), 'seed')
ON CONFLICT DO NOTHING;

INSERT INTO message_events (tenant_id, profile_id, campaign_id, channel, event_type, event_time, attributes)
VALUES
  ('260217000000ups00000001', '260218120000000100000001', '260218120000cmp000000001', 'sms', 'sent', now() - interval '2 days', '{"provider":"seed","template_id":"tmpl_a"}'::jsonb),
  ('260217000000ups00000001', '260218120000000100000001', '260218120000cmp000000001', 'sms', 'delivered', now() - interval '2 days' + interval '2 minute', '{"provider":"seed","template_id":"tmpl_a"}'::jsonb),
  ('260217000000ups00000001', '260218120000000100000002', '260218120000cmp000000002', 'email', 'failed', now() - interval '1 day', '{"provider":"seed","template_id":"tmpl_b"}'::jsonb)
ON CONFLICT DO NOTHING;
