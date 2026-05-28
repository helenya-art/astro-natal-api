-- Migration 009: Short forecast cache (day/week/month in one JSON column)
alter table public.natal_charts
  add column if not exists forecast_short_cache jsonb default null;
