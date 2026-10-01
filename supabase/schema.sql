-- Run once in the Supabase dashboard: SQL Editor -> New query -> paste -> Run.
-- The server talks to Supabase with the service-role key, which bypasses RLS.
-- RLS is enabled with no policies, so the public (anon) API key can't read or write this data.

create table if not exists public.requests (
  id         bigint generated always as identity primary key,
  filename   text,
  created_at timestamptz not null default now(),
  total      integer not null default 0
);

create table if not exists public.listings (
  id         bigint generated always as identity primary key,
  request_id bigint not null references public.requests(id) on delete cascade,
  row_index  integer not null,
  sku        text,
  vendor     text,
  raw_row    text,
  listing    jsonb,
  status     text not null check (status in ('pending', 'approved', 'rejected', 'error')),
  error      text,
  note       text,
  updated_at timestamptz not null default now()
);

create index if not exists listings_request_id_idx on public.listings (request_id, row_index);

alter table public.requests enable row level security;
alter table public.listings enable row level security;
revoke all on public.requests, public.listings from anon, authenticated;

-- Make the new tables visible to the API immediately (otherwise: "not found in the schema cache").
notify pgrst, 'reload schema';
