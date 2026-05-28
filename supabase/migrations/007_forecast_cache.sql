-- Migration 007: Forecast cache columns
alter table public.natal_charts
  add column if not exists forecast_cache jsonb default null,
  add column if not exists forecast_cached_at timestamptz default null;
