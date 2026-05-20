# 04 — Data Model

All tables Postgres. Migrations in `/api/migrations/` (use Alembic). Apply with `alembic upgrade head`.

## Conventions

- All tables have `id uuid primary key default gen_random_uuid()`
- All tables (except `users`) have `user_id uuid not null references auth.users(id) on delete cascade`
- All tables have `created_at timestamptz not null default now()` and `updated_at timestamptz not null default now()`
- All tables have RLS enabled with `user_id = auth.uid()` policies
- Soft delete via `deleted_at timestamptz null` where applicable
- Snake_case column names

## Tables

### `folders`
```sql
create table folders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  parent_id uuid references folders(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, parent_id, name)
);
create index on folders(user_id, parent_id);
```

### `tags`
```sql
create table tags (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now(),
  unique (user_id, name)
);
```

### `documents`
```sql
create type document_status as enum (
  'uploaded', 'extracting_text', 'classified', 'schema_built',
  'extracted', 'verified', 'integrated', 'vectorized', 'ready', 'failed'
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  folder_id uuid references folders(id) on delete set null,
  file_hash text not null,             -- SHA256 of file bytes
  original_filename text not null,
  mime_type text not null,
  file_type text not null,             -- normalized: pdf, image, docx, xlsx, pptx, csv, txt
  size_bytes bigint not null,
  storage_path text not null,          -- supabase storage key
  user_note text,
  status document_status not null default 'uploaded',
  failure_reason text,
  doc_type text,                       -- classifier output (e.g., passport, marriage_certificate, x_ray_report)
  domain text,                         -- personal | medical | legal | financial | professional | educational | other
  country text,                        -- ISO 3166-1 alpha-2 or null
  language text,                       -- ISO 639-1
  is_scanned boolean,
  is_handwritten boolean,
  schema_json jsonb,                   -- schema architect output
  summary text,                        -- short LLM summary (set early so search works immediately)
  raw_text text,                       -- full extracted text (may be long)
  full_text_tsv tsvector,              -- for BM25 search
  metadata jsonb default '{}'::jsonb,  -- catch-all
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  unique (user_id, file_hash)          -- dedupe per user
);

create index on documents(user_id, status);
create index on documents(user_id, folder_id);
create index on documents(user_id, file_type);
create index on documents(user_id, doc_type);
create index documents_tsv_idx on documents using gin(full_text_tsv);
create index documents_summary_trgm_idx on documents using gin(summary gin_trgm_ops);
```

### `document_tags`
```sql
create table document_tags (
  document_id uuid not null references documents(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  primary key (document_id, tag_id)
);
```

### `extracted_fields`
```sql
create table extracted_fields (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  document_id uuid not null references documents(id) on delete cascade,
  field_name text not null,            -- e.g., passport_number, holder_name, dob
  field_value text,                    -- always stored as text; parse on read
  field_type text not null,            -- string | number | date | enum | identifier
  confidence numeric(3,2),             -- 0.00 to 1.00, set by verifier
  needs_retry boolean default false,
  retry_count int default 0,
  reasoning text,                      -- verifier's note
  is_entity_ref boolean default false, -- true if this field references a person/org
  created_at timestamptz not null default now()
);
create index on extracted_fields(document_id);
create index on extracted_fields(user_id, field_name, field_value);
```

### `entities`
```sql
create table entities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  entity_type text not null,           -- person | organization | asset | project | patient | client | case | vehicle | location | other
  canonical_name text not null,
  aliases jsonb default '[]'::jsonb,   -- ["Priya", "Mrs. Shah", ...]
  attributes jsonb default '{}'::jsonb, -- type-specific: dob, gender, address, etc.
  identifiers jsonb default '{}'::jsonb, -- hard keys: { passport_number: "...", pan: "...", isin: "..." }
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on entities(user_id, entity_type);
create index entities_name_trgm_idx on entities using gin(canonical_name gin_trgm_ops);
create index entities_aliases_gin_idx on entities using gin(aliases);
create index entities_identifiers_gin_idx on entities using gin(identifiers);
```

### `entity_relationships`
```sql
create table entity_relationships (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  from_entity_id uuid not null references entities(id) on delete cascade,
  to_entity_id uuid not null references entities(id) on delete cascade,
  relation_type text not null,         -- spouse_of, child_of, parent_of, sibling_of, patient_of, client_of, member_of, owner_of, located_at, etc.
  attributes jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, from_entity_id, to_entity_id, relation_type)
);
create index on entity_relationships(user_id, from_entity_id);
create index on entity_relationships(user_id, to_entity_id);
```

### `facts`
```sql
create table facts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  entity_id uuid not null references entities(id) on delete cascade,
  source_document_id uuid not null references documents(id) on delete cascade,
  field_name text not null,            -- passport_number, expiry_date, salary, etc.
  field_value text not null,
  field_type text not null,
  confidence numeric(3,2),
  valid_from timestamptz default now(),
  valid_until timestamptz,             -- NULL = current; set when superseded
  created_at timestamptz not null default now()
);
create index on facts(user_id, entity_id, field_name);
create index on facts(user_id, entity_id, field_name, valid_until); -- "current value of X"
```

### `document_entities`
```sql
create table document_entities (
  document_id uuid not null references documents(id) on delete cascade,
  entity_id uuid not null references entities(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null,                  -- subject | author | mentioned | witness | beneficiary | other
  primary key (document_id, entity_id, role)
);
create index on document_entities(entity_id);
```

### `chunks`
```sql
create extension if not exists vector;

create table chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  document_id uuid not null references documents(id) on delete cascade,
  chunk_index int not null,
  text text not null,
  metadata jsonb default '{}'::jsonb,  -- page number, source field, etc.
  embedding vector(1536) not null,     -- OpenAI text-embedding-3-small
  created_at timestamptz not null default now()
);
create index on chunks(document_id, chunk_index);
create index chunks_embedding_idx on chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
```

### `document_pipeline_events`
```sql
create table document_pipeline_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  document_id uuid not null references documents(id) on delete cascade,
  stage text not null,                 -- text_extracted | classified | schema_built | extracted | verified | integrated | vectorized | ready | failed | retry
  status text not null default 'success',  -- success | failure
  details jsonb default '{}'::jsonb,
  trace_id text,                       -- langfuse trace id
  duration_ms int,
  created_at timestamptz not null default now()
);
create index on document_pipeline_events(document_id, created_at);
create index on document_pipeline_events(user_id, created_at);
```

## RLS policies

Apply this pattern to every table with `user_id`:

```sql
alter table <table_name> enable row level security;

create policy "user can read own"
  on <table_name> for select using (user_id = auth.uid());

create policy "user can insert own"
  on <table_name> for insert with check (user_id = auth.uid());

create policy "user can update own"
  on <table_name> for update using (user_id = auth.uid());

create policy "user can delete own"
  on <table_name> for delete using (user_id = auth.uid());
```

For `chunks`, also enforce via `document_id` traversal if needed. Workers connect using the service role and must always include `user_id` filters explicitly in queries.

## Migrations strategy

- One migration per logical change. Name: `YYYYMMDD_HHmm_<slug>.sql`.
- Each migration starts with `begin;` and ends with `commit;`.
- Reverse migrations not required for Phase 1 (we can drop and rebuild dev DB).
- Run migrations via Alembic from `api/`. Track state in `alembic_version` table.

## Storage layout

Supabase Storage bucket: `user-uploads`.
Path pattern: `<user_id>/<document_id>/<safe_filename>`.
Policy: only authenticated users can read/write under their own `user_id/` prefix.

## Useful queries (reference)

```sql
-- Find current passport number for entity
select field_value from facts
where user_id = $1 and entity_id = $2
  and field_name = 'passport_number'
  and valid_until is null;

-- Find all family members of current user
-- (assumes a "self" entity exists for the user)
select e.* from entities e
join entity_relationships r on r.to_entity_id = e.id
where r.user_id = $1
  and r.from_entity_id = (select id from entities where user_id = $1 and entity_type = 'person' and attributes->>'is_self' = 'true');

-- Hybrid search: docs matching tsv + filtered by entity
select d.* from documents d
join document_entities de on de.document_id = d.id
where d.user_id = $1
  and de.entity_id = $2
  and d.full_text_tsv @@ plainto_tsquery('english', $3)
order by ts_rank(d.full_text_tsv, plainto_tsquery('english', $3)) desc
limit 20;
```
