-- Tables for Voice & Truth, War Room and Prep. Run once in the Supabase SQL editor.
-- All are written through the service key only (row-level security on, no public policies).

create table if not exists public.speech_archive (
  id           uuid primary key default gen_random_uuid(),
  title        text not null,
  event_date   date,
  place        text,
  speaker      text,
  file_sha256  text,
  duration_s   numeric,
  language     text,
  link         text,           -- where the video is published, for jumping to the moment
  segments     jsonb,          -- [{start, end, text}]
  fingerprint  text,           -- compressed audio landmark hashes (base64)
  created_at   timestamptz not null default now()
);

create table if not exists public.promises (
  id           uuid primary key default gen_random_uuid(),
  archive_id   uuid references public.speech_archive(id) on delete set null,
  said_on      date,
  said_at_s    numeric,
  quote        text,
  promise      text not null,
  area         text,
  due          text,
  status       text not null default 'Suggested',   -- Suggested, Confirmed, In progress, Done, Late, Dropped, Rejected
  evidence     text,
  whose        text not null default 'Ours',        -- Ours or Rival
  created_at   timestamptz not null default now()
);

create table if not exists public.ledger (
  id           uuid primary key default gen_random_uuid(),
  seq          bigint not null,
  kind         text not null,          -- meeting, spend, work, statement
  body         jsonb not null,
  prev_hash    text not null,
  hash         text not null unique,
  created_at   timestamptz not null default now()
);

create table if not exists public.contacts (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  role         text,
  department   text,
  phone        text,
  area         text,
  notes        text,
  created_at   timestamptz not null default now()
);

create table if not exists public.field_events (
  id           uuid primary key default gen_random_uuid(),
  event_date   date not null,
  kind         text,                  -- rally, padayatra, press meet, visit
  place        text not null,
  ward         text,
  who          text,                  -- Ours or a rival party
  notes        text,
  created_at   timestamptz not null default now()
);

create table if not exists public.message_tests (
  id           uuid primary key default gen_random_uuid(),
  question     text not null,
  variants     jsonb not null,
  status       text not null default 'Open',
  created_at   timestamptz not null default now()
);

create table if not exists public.message_responses (
  id           uuid primary key default gen_random_uuid(),
  test_id      uuid references public.message_tests(id) on delete cascade,
  variant      int not null,
  rating       int,
  would_share  boolean,
  created_at   timestamptz not null default now()
);

create table if not exists public.voice_tickets (
  id           uuid primary key default gen_random_uuid(),
  ticket_no    text not null,
  language     text,
  transcript   text,
  summary_en   text,
  summary_te   text,
  category     text,
  area         text,
  department   text,
  urgency      text,
  status       text not null default 'Open',
  consent      boolean not null default false,
  issue_id     uuid,
  created_at   timestamptz not null default now()
);

alter table public.speech_archive   enable row level security;
alter table public.promises         enable row level security;
alter table public.ledger           enable row level security;
alter table public.contacts         enable row level security;
alter table public.field_events     enable row level security;
alter table public.message_tests    enable row level security;
alter table public.message_responses enable row level security;
alter table public.voice_tickets    enable row level security;
