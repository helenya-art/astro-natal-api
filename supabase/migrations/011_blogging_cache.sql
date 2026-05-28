-- Migration 011: Blogging potential analysis cache
alter table public.natal_charts
  add column if not exists blogging_cache jsonb default null;
