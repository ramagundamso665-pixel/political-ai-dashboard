-- Run once in the Supabase SQL editor for the dashboard's project.
-- Backs the Manage Leaders page (views/leaders.py). Only the dashboard's service
-- key reads or writes it; row-level security with no policies keeps everyone else out.

create table if not exists public.manual_leaders (
  id            uuid primary key default gen_random_uuid(),
  display_name  text not null unique,
  term          text,
  headline_terms text[],
  exclude_terms  text[],
  created_at    timestamptz not null default now()
);

alter table public.manual_leaders enable row level security;
