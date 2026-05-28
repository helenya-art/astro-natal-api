-- Migration 008: Leadership style cache column
alter table public.natal_charts
  add column if not exists leadership_cache jsonb default null;
