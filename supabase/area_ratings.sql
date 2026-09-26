-- Run once in the Supabase SQL editor for the dashboard's project.
-- Backs the WhatsApp "rate my area" bot (whatsapp_bot/) and the Area Ratings page.
-- Phone numbers are never stored: only a salted hash, which lets the bot allow one rating a week per person
-- and delete a person's answers when they send STOP. Only the service key reads or writes these tables.

create table if not exists public.area_ratings (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  week        text not null,              -- ISO week, e.g. 2026-W39
  phone_hash  text not null,
  area        text not null,
  issue       text not null,              -- the issue that bothers them most this week
  rating      int  not null check (rating between 1 and 5),
  language    text not null default 'en',
  unique (phone_hash, week)
);

create table if not exists public.wa_sessions (
  phone_hash  text primary key,
  step        text not null default 'start',
  language    text not null default 'en',
  issue       text,
  area        text,
  updated_at  timestamptz not null default now()
);

alter table public.area_ratings enable row level security;
alter table public.wa_sessions enable row level security;
