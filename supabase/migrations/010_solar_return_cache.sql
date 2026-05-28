-- Migration 010: Solar return (yearly chart) cache
alter table public.natal_charts
  add column if not exists solar_return_cache jsonb default null,
  add column if not exists solar_return_year integer default null;
