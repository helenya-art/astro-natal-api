-- Astro Self Map — Initial Schema
-- Auth: Firebase (user_id = Firebase UID string, not Supabase auth.users)

-- Natal charts
create table public.natal_charts (
  id                  uuid primary key default gen_random_uuid(),
  user_id             text not null,          -- Firebase UID
  name                text not null,
  birth_date          text not null,
  birth_time          text,
  birth_time_exact    boolean not null default true,
  birth_place         text not null,
  latitude            double precision not null,
  longitude           double precision not null,
  chart_data          jsonb not null,
  interpretation      jsonb,
  character_type      text,
  character_image_url text,
  created_at          timestamptz not null default now()
);

-- Chat sessions
create table public.chat_sessions (
  id          uuid primary key default gen_random_uuid(),
  chart_id    uuid not null references public.natal_charts(id) on delete cascade,
  user_id     text not null,          -- Firebase UID
  messages    jsonb not null default '[]',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Indexes
create index natal_charts_user_id_idx on public.natal_charts(user_id);
create index chat_sessions_chart_id_idx on public.chat_sessions(chart_id);
create index chat_sessions_user_id_idx on public.chat_sessions(user_id);

-- Storage bucket for character images
insert into storage.buckets (id, name, public)
values ('astro-images', 'astro-images', true)
on conflict do nothing;

-- Public read for images (CDN delivery)
create policy "Public read astro-images"
  on storage.objects for select
  using (bucket_id = 'astro-images');
