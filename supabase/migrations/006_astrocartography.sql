-- Migration 006: Astrocartography cache column
alter table public.natal_charts
  add column if not exists astrocartography jsonb default null;
