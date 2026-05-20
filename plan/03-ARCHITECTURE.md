# 03 — Architecture

## System diagram

```
┌──────────────┐
│   Browser    │
└──────┬───────┘
       │  HTTPS
       ▼
┌──────────────────────┐         ┌────────────────────┐
│  Next.js (Vercel)    │◄────────│  Supabase          │
│  - Pages + UI        │ Realtime│  - Auth            │
│  - API routes (BFF)  │         │  - Postgres+pgvector│
│  - Server actions    │         │  - Storage (S3-API) │
└──────┬───────────────┘         │  - Realtime         │
       │                         └─────────▲──────────┘
       │  POST /enqueue                    │ writes
       ▼                                   │
┌──────────────────────┐                   │
│  FastAPI (Railway)   │───────────────────┤
│  - Public REST API   │                   │
│  - /chat (streaming) │                   │
│  - /enqueue          │                   │
└──────┬───────────────┘                   │
       │                                   │
       │ enqueue job                       │
       ▼                                   │
┌──────────────────────┐                   │
│   Redis (queue)      │                   │
└──────┬───────────────┘                   │
       │                                   │
       │ pop job                           │
       ▼                                   │
┌──────────────────────┐                   │
│   arq worker         │───────────────────┘
│   (Railway)          │
│  - 5-agent pipeline  │──────► Anthropic API
│  - vectorization     │──────► OpenAI Embeddings API
│  - knowledge layer   │──────► Langfuse (traces)
└──────────────────────┘
```

## Component responsibilities

### Next.js
- **Auth UI** via Supabase Auth helpers (`@supabase/ssr`)
- **All user-facing routes** (`/`, `/library`, `/document/[id]`, `/chat`, `/graph`)
- **Direct uploads** to Supabase Storage from the browser (signed URL) — never proxied through Next.js
- **API routes** (`/api/*`) act as a thin BFF (Backend-For-Frontend): create document row, call FastAPI `/enqueue`, return to client. They do not run business logic.
- **Realtime subscriptions** to `documents` and `document_pipeline_events` tables for live UI updates

### FastAPI
- **Public REST API** consumed by Next.js BFF + frontend chat
- Endpoints (see API Contracts below)
- **No file storage**, no auth UI. Stateless except for in-process caches.
- All requests authenticated via Supabase JWT (verify with Supabase JWKs) OR via a shared `BACKEND_API_KEY` for server-to-server calls from Next.js

### Worker (arq)
- Picks up document processing jobs from Redis
- Runs the **5-agent pipeline** (see `06-AGENT-HARNESS.md`)
- Writes intermediate state to Postgres after each stage
- Inserts pipeline event rows to `document_pipeline_events` (triggers Realtime)
- Emits Langfuse traces

### Supabase
- **Auth**: Email/password to start. Magic link optional.
- **Postgres**: Single DB. RLS enforced.
- **Storage**: One bucket `user-uploads`. Path: `<user_id>/<doc_id>/<original_filename>`.
- **Realtime**: Subscriptions on `documents` and `document_pipeline_events` per `user_id`.

## Data flows

### Flow 1: Document upload

```
1. User selects file in browser
2. Next.js requests signed upload URL from Supabase Storage (RPC or REST)
3. Browser uploads directly to Supabase Storage
4. On upload complete, Next.js calls POST /api/documents
   - Creates `documents` row with status=`uploaded`
   - Computes file hash; if duplicate, returns existing doc id
5. Next.js calls FastAPI POST /enqueue with doc_id
6. FastAPI pushes job to Redis (arq.enqueue)
7. FastAPI returns 202; Next.js returns to client
8. Client sees the new doc in the grid via Realtime
```

### Flow 2: Pipeline processing

```
1. arq worker pops job
2. Loads document row + downloads file from Storage to /tmp
3. Stage A — Extract raw text/images (deterministic)
4. Stage B — Classifier agent (Haiku)
   - Updates doc with: doc_type, domain, language, quality
   - Inserts pipeline_event(stage='classified')
5. Stage C — Schema architect agent (Sonnet)
   - Stores schema JSON on document row
   - Inserts pipeline_event(stage='schema_built')
6. Stage D — Extractor agent (Sonnet, multimodal)
   - Inserts rows into `extracted_fields`
   - Inserts pipeline_event(stage='extracted')
7. Stage E — Verifier agent (Haiku)
   - Updates `extracted_fields.confidence`
   - If any fields need retry: re-run extractor on those fields, max 2 retries
   - Inserts pipeline_event(stage='verified')
8. Stage F — Knowledge integrator agent (Sonnet)
   - Resolves entities; creates/updates `entities` and `facts`
   - Inserts `document_entities` links
   - Inserts pipeline_event(stage='integrated')
9. Stage G — Vectorization (deterministic)
   - Chunks raw text + extracted summary
   - Calls OpenAI embeddings batch
   - Inserts into `chunks` with embeddings
   - Inserts pipeline_event(stage='vectorized')
10. Updates doc status=`ready`
```

Each pipeline_event row is observable via Realtime → frontend animates the stages live.

### Flow 3: Search and filter

See `05-CODING-STANDARDS.md` for the resolver implementation. High level:

```
1. User types term, hits Enter
2. Frontend calls GET /api/search?q=<term>&chips=<json>
3. BFF calls FastAPI POST /search with current chip set
4. Resolver (in FastAPI services/search/resolver.py):
   - Looks up term in in-memory facet vocabulary (per user, lazy-loaded)
   - Returns matching facet(s) and the new chip
   - On ambiguity or zero clean matches, calls Haiku to parse query → chips
5. Builds SQL with the AND-composed chips
6. Returns results paginated
```

### Flow 4: Chat

```
Single-document chat:
  POST /chat with {doc_id, message, history}
  → vector search within that doc's chunks
  → Claude with context = doc summary + top chunks + extracted fields
  → SSE stream back to client

All-documents chat:
  POST /chat with {message, history}
  → resolve any entities/relationships in message via KG
  → hybrid retrieve: KG facts + top chunks across user's docs
  → Claude with context = KG snippets + chunks
  → cite source documents in response
  → SSE stream back to client
```

## API contracts

These contracts are **frozen** at start of Day 2. Parallel FE/BE tracks build against this contract.

### POST `/api/documents` (Next.js BFF)
```json
Request: {
  "filename": "string",
  "mime_type": "string",
  "size_bytes": 123,
  "file_hash": "sha256",
  "storage_path": "user_id/doc_id/filename",
  "folder_id": "uuid | null",
  "user_note": "string | null",
  "tag_ids": ["uuid"]
}
Response: { "doc_id": "uuid", "is_duplicate": false }
```

### POST `/enqueue` (FastAPI)
```json
Request: { "doc_id": "uuid" }
Response: { "job_id": "string", "status": "queued" }
```

### POST `/search` (FastAPI)
```json
Request: {
  "term": "string",
  "chips": [
    { "facet": "file_type | folder | tag | doc_type | entity | date | content", "value": "string", "display": "string" }
  ],
  "limit": 50,
  "offset": 0
}
Response: {
  "resolved_chip": { "facet": "...", "value": "...", "display": "..." } | null,
  "documents": [ /* doc objects */ ],
  "total": 123,
  "facet_breakdown": { /* counts per facet for sidebar */ }
}
```

### POST `/chat` (FastAPI, SSE stream)
```json
Request: {
  "scope": "document | all",
  "doc_id": "uuid | null",
  "messages": [ { "role": "user|assistant", "content": "..." } ]
}
Response (SSE):
  event: token, data: "<text chunk>"
  event: citation, data: { "doc_id": "uuid", "chunk_id": "uuid" }
  event: done, data: { "usage": {...} }
```

### GET `/api/folders` (Next.js BFF — wraps Supabase queries)
Returns user's folder tree.

### POST `/api/folders`, PATCH `/api/folders/:id`, DELETE `/api/folders/:id`
CRUD operations on folders.

### GET, POST, DELETE `/api/tags`
CRUD operations on tags.

### GET `/api/graph?entity_id=<id>` (Next.js BFF)
Returns entity, its facts, related entities, related documents. Used by the graph view.

## Realtime channels

- `documents:<user_id>` — INSERT/UPDATE on user's documents (for grid live updates)
- `pipeline_events:<user_id>` — INSERT on `document_pipeline_events` filtered by user_id (for per-doc stage animation)

## Auth flow

1. User signs up/in via Supabase Auth on Next.js
2. Supabase issues JWT in cookie
3. Next.js BFF calls Supabase directly using server client (RLS applies)
4. When Next.js BFF calls FastAPI, it passes:
   - The user's JWT in `Authorization: Bearer <jwt>` (FastAPI verifies)
   - OR a shared `X-Backend-Key` for server-to-server calls (e.g., webhook handlers)
5. FastAPI workers use the Supabase service-role key for DB writes (jobs run on user's behalf; RLS bypassed but `user_id` always explicit)
