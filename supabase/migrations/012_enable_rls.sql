-- Migration 012: Enable Row Level Security on all tables
--
-- Our backend uses service_role key which bypasses RLS automatically.
-- No application code changes needed.
-- This prevents any direct Supabase client access (anon / authenticated roles).

-- Enable RLS
alter table public.natal_charts       enable row level security;
alter table public.chat_sessions      enable row level security;
alter table public.user_subscriptions enable row level security;

-- Revoke the overly permissive grants given in migration 004.
-- We do not use Supabase Auth (auth is Firebase), so the authenticated
-- role should have no access to any table.
revoke select, insert, update, delete
  on public.natal_charts from authenticated;

revoke select, insert, update, delete
  on public.chat_sessions from authenticated;

revoke select
  on public.user_subscriptions from authenticated;

-- service_role grants remain (backend needs them, service_role bypasses RLS).
-- No RLS policies are added: with RLS enabled and no ALLOW policy,
-- all access is denied by default for every non-service_role connection.
