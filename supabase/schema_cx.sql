-- CX Support Copilot (Step 3). Run once in the Supabase SQL Editor, after supabase/schema.sql.
-- Same security model as schema.sql: RLS on, no policies, anon/authenticated revoked;
-- the server uses the service-role key. Phone numbers and order data are personal data.
-- The catalogue is NOT duplicated: the copilot reads approved rows of public.listings.

create table if not exists public.cx_customers (
  customer_id bigint generated always as identity primary key,
  phone       text not null unique check (phone ~ '^[0-9]{10}$'),  -- normalised: last 10 digits
  name        text not null,
  created_at  timestamptz not null default now()
);

create table if not exists public.cx_orders (
  id                bigint generated always as identity primary key,
  order_id          text not null unique,
  customer_id       bigint not null references public.cx_customers(customer_id) on delete cascade,
  sku_code          text not null,          -- joins to listings.sku (approved rows only)
  size_ordered      text,
  status            text not null check (status in
                    ('PLACED','SHIPPED','IN_TRANSIT','OUT_FOR_DELIVERY','DELIVERED','RETURN_REQUESTED','CANCELLED')),
  carrier           text,
  awb               text,
  ordered_at        timestamptz not null default now(),
  expected_delivery date
);
create index if not exists cx_orders_customer_idx on public.cx_orders (customer_id, ordered_at desc);
create index if not exists listings_sku_status_idx on public.listings (sku, status);

create table if not exists public.cx_reply_log (
  id           bigint generated always as identity primary key,
  customer_id  text,
  phone_masked text,
  category     text,
  draft        text,
  final        text,
  edited       boolean,
  needs_human  boolean,
  reason       text,
  created_at   timestamptz not null default now()
);

alter table public.cx_customers enable row level security;
alter table public.cx_orders    enable row level security;
alter table public.cx_reply_log enable row level security;
revoke all on public.cx_customers, public.cx_orders, public.cx_reply_log from anon, authenticated;

notify pgrst, 'reload schema';
