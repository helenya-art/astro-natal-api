-- Migration 003: enforce one chat session per (chart_id, user_id)
-- Prevents duplicate sessions from concurrent requests

alter table public.chat_sessions
  add constraint chat_sessions_chart_user_unique
  unique (chart_id, user_id);
