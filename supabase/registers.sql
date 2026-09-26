-- Run once in the Supabase SQL editor for the dashboard's project.
-- Backs the RTI Tracker and Local Issues pages. Only the dashboard's service key
-- reads or writes these; row-level security with no policies keeps everyone else out.

create table if not exists public.rti_requests (
  id            uuid primary key default gen_random_uuid(),
  subject       text not null,
  department    text,
  filed_on      date,
  reply_due_on  date,
  status        text not null default 'Filed',
  reply_summary text,
  reference_no  text,
  division      text,
  filed_by      text,
  notes         text,
  created_at    timestamptz not null default now()
);

create table if not exists public.local_issues (
  id            uuid primary key default gen_random_uuid(),
  title         text not null,
  category      text,
  division      text,
  booth         text,
  location      text,
  severity      text not null default 'Medium',
  status        text not null default 'Open',
  source        text,
  details       text,
  link          text,
  reported_on   date,
  linked_rti_id uuid,
  created_at    timestamptz not null default now()
);

alter table public.rti_requests enable row level security;
alter table public.local_issues enable row level security;
