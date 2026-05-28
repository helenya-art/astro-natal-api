-- Migration 002: subscription tracking (updated via RevenueCat webhook)
-- user_id = Firebase UID (text)

create table public.user_subscriptions (
  user_id        text primary key,   -- Firebase UID
  is_premium     boolean not null default false,
  rc_customer_id text,
  expires_at     timestamptz,
  updated_at     timestamptz not null default now()
);

create index user_subscriptions_user_id_idx on public.user_subscriptions(user_id);
