-- Migration 013: Track background premium generation failures
alter table public.natal_charts
  add column if not exists premium_generation_failed boolean default null;
