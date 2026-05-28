-- Migration 005: Premium interpretation column
alter table public.natal_charts
  add column if not exists premium_interpretation jsonb default null;
