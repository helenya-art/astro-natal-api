-- Migration 004: Explicit grants for Supabase Data API
-- Required before October 30, 2026 (Supabase policy change).
-- Our backend uses service_role key (bypasses RLS), so we're not
-- immediately affected — but explicit grants future-proof the setup.

-- natal_charts
grant select, insert, update, delete
  on public.natal_charts to service_role;

grant select, insert, update, delete
  on public.natal_charts to authenticated;

-- chat_sessions
grant select, insert, update, delete
  on public.chat_sessions to service_role;

grant select, insert, update, delete
  on public.chat_sessions to authenticated;

-- user_subscriptions (read-only for authenticated users — writes via webhook only)
grant select, insert, update, delete
  on public.user_subscriptions to service_role;

grant select
  on public.user_subscriptions to authenticated;
