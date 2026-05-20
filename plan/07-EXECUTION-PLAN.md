# 07 — Execution Plan (Sequential)

This is the sequential plan. If running everything in a single Claude Code session, follow this top-to-bottom. If running parallel sessions, see `08-PARALLEL-TRACKS.md` and use this file as the reference for what each task entails.

Each task has an ID like `D1-S-01` (Day 1, Setup, task 01). Tasks that can run in parallel are marked. PROGRESS.md tracks state with these IDs.

## Day 1 — Foundations (sequential, ~5 hours)

Single session. No parallelism. Goal: every service running locally and in production, no business logic yet.

### `D1-01` Repo bootstrap (30 min)
- Create monorepo with `/web` and `/api` and `/plan`
- Init git, add `.gitignore` (Node + Python + envs + data)
- Add `docker-compose.yml` for local Redis and Langfuse
- Create `.env.example` per `02-TECH-STACK.md`
- Push to GitHub

### `D1-02` Supabase setup (45 min)
- Create Supabase project
- Enable `vector`, `pg_trgm`, `unaccent` extensions
- Create storage bucket `user-uploads` with policy: authenticated users can RW under their own `user_id/` prefix
- Save URL, anon key, service-role key to `.env`
- Apply auth provider settings (email/password on)

### `D1-03` Apply data model migrations (45 min)
- Set up Alembic in `/api`
- Translate every table from `04-DATA-MODEL.md` into the initial migration
- Apply migrations to dev DB
- Add RLS policies migration
- Run a quick sanity check: `psql` and `\dt`

### `D1-04` API scaffold (45 min)
- FastAPI app with `/health`, settings module, structured logging
- Async SQLAlchemy session dependency
- Anthropic and OpenAI clients (test calls in `__main__` blocks)
- Supabase server-side client (service-role)
- Langfuse client
- Dockerfile

### `D1-05` Worker scaffold (30 min)
- arq `WorkerSettings`
- Single dummy task that logs and updates a doc status
- Wire to same DB and Redis as API
- Verify a job round-trips end-to-end

### `D1-06` Web scaffold (45 min)
- Next.js 15 with App Router, TypeScript strict
- Tailwind + shadcn/ui init (button, input, dialog, dropdown, toast, card)
- Supabase client + middleware (cookie-based session)
- Login + signup pages (functional, ugly)
- Protected `/` route that shows "Hello {user.email}"
- Sign-out works

### `D1-07` Deploy targets (30 min)
- Vercel project linked to repo, web/ as root
- Railway project: API service, worker service, Redis plugin, Langfuse service
- Set env vars in both
- Deploy `main`. Verify `/health` returns 200 on Railway. Verify `/` requires login on Vercel.

End-of-day-1 check: log in on prod, see empty dashboard. Run `arq` locally and queue a dummy job — see it complete.

---

## Day 2 — Backend core + Frontend upload UI (~5 hours)

**Parallel possible** (see `08-PARALLEL-TRACKS.md`). Sequential order below.

### `D2-BE-01` Document upload endpoint (60 min)
- `POST /api/documents` (Next.js BFF): validates body with zod, computes file_hash check, calls Supabase to insert document row, calls FastAPI `/enqueue`
- `POST /enqueue` (FastAPI): validates doc_id, enqueues arq job
- Implement `documents_repo.py` create/get/update_status
- Add `errors.py` with the hierarchy in `05-CODING-STANDARDS.md`
- Test with curl + a fake doc_id

### `D2-BE-02` File-type-specific parsers (90 min)
- `parsing/router.py`: MIME → parser dispatch
- `parsing/pdf.py`: pdfplumber for text + tables, pymupdf for page-as-image fallback, pikepdf for password unlock attempt
- `parsing/image.py`: just load image bytes (no OCR yet)
- `parsing/docx.py`, `parsing/pptx.py`, `parsing/xlsx.py`, `parsing/csv.py`, `parsing/txt.py`
- `RawExtraction` dataclass: { text, tables, page_images, page_count, structured }
- Unit tests on a fixture per file type

### `D2-BE-03` Classifier agent + integration (45 min)
- Implement `agents/base.py` per `06-AGENT-HARNESS.md`
- Implement `agents/classifier.py` and `agents/prompts/classifier.md`
- Wire into a stub pipeline that just classifies and updates doc fields
- Test on a sample PDF

### `D2-BE-04` Pipeline state machine + worker task (45 min)
- `services/pipeline/state_machine.py`: status transitions
- `services/pipeline/orchestrator.py`: drives one stage at a time, persists between
- `worker/tasks.py`: `process_document(doc_id)` job
- `events_repo.py`: insert pipeline events
- Verify: upload via curl → see status walk through `uploaded → extracting_text → classified` in DB

### `D2-FE-01` App shell + library page (60 min)
- App layout: top bar (logo, user menu, search input), left sidebar (folders + tags)
- `/library` page with empty state ("Drop files to begin")
- Implement `lib/supabase/client.ts` and `server.ts`
- Folder list query via Supabase from client component
- Wire shadcn toast for errors

### `D2-FE-02` Upload widget + signed URL flow (60 min)
- `components/upload/Dropzone.tsx` with react-dropzone
- On drop: validate MIME, compute SHA256 in browser (via SubtleCrypto)
- Request signed upload URL from Supabase Storage (use `supabase.storage.from(...).createSignedUploadUrl`)
- Upload directly to Storage
- Call `POST /api/documents` with metadata
- Show progress per file
- Trigger optimistic insert into library grid

### `D2-FE-03` Document grid (60 min)
- `components/library/DocumentGrid.tsx`: virtualized grid of `DocumentCard`s
- `DocumentCard`: thumbnail, name, type icon, status badge, tag chips
- Subscribe to Realtime channel `documents:<user_id>` to stream new/updated docs in
- Status badge updates live as pipeline progresses

End-of-day-2 check: upload a PDF → see it appear in grid → classifier runs → status moves to `classified`. No extraction yet.

---

## Day 3 — Full harness + Knowledge layer (~5 hours)

**Parallel possible** for backend agents and knowledge-graph view UI.

### `D3-BE-01` Schema architect + Extractor agents (75 min)
- Implement both with their prompts
- Wire into orchestrator: text_extracted → classified → schema_built → extracted
- Add `extracted_fields_repo.py` (insert + bulk insert + get-by-document)
- Test on 3 different fixture documents

### `D3-BE-02` Verifier + targeted retry (60 min)
- Implement Verifier agent
- In orchestrator: after extraction, run verifier, then if any field needs_retry and retry_count < 2, re-run extractor with retry prompt augmentation
- Persist verifier output to `extracted_fields.confidence`, `reasoning`
- Test: deliberately blur a fixture image and confirm retry triggers

### `D3-BE-03` Knowledge Integrator + entity resolution (75 min)
- Implement Knowledge Integrator
- `services/knowledge/entity_resolver.py`: pre-filter candidate entities via SQL (name trigram match + identifier hash match) before sending to LLM
- After LLM decision: write entities/facts/relationships through `entities_repo.py`, `facts_repo.py`
- Fact versioning: when an entity already has a fact with same field_name, set old `valid_until = now()`, insert new fact
- Test: upload passport, then upload "renewed passport" with same passport_number → confirm new fact, old fact superseded

### `D3-BE-04` Vectorization step (30 min)
- After integration: chunk text + insert embeddings
- Use OpenAI batch (one API call per doc)
- Insert rows into `chunks` table
- Update doc status to `ready`
- Verify: a vector search returns the doc

### `D3-FE-01` Document detail page (60 min)
- `/document/[id]` route
- Show: file preview (PDF viewer, image lightbox, or "open in new tab" link), extracted fields table with confidence pills, related entities, pipeline trace timeline
- Realtime subscription to update pipeline timeline as worker progresses
- Edit-extracted-field button (Phase 1: just allow override and save; no agent retry yet)

### `D3-FE-02` Graph view (60 min)
- `/graph` route
- Use a simple force-directed layout (use `react-force-graph` or even d3 directly)
- Nodes = entities, sized by # of linked docs; edges = relationships
- Click node → side panel with entity details and docs

End-of-day-3 check: upload a passport, marriage certificate, birth certificate. See entities populate, with spouse/child relations drawn in the graph.

---

## Day 4 — Search + Chat + Integration (~5 hours)

Sequential. Integration day.

### `D4-01` Search resolver (60 min)
- `services/search/vocab_cache.py`: load per-user facet vocabulary lazily (file_types, folder names, tag names, doc_types, entity names + aliases, common relation terms like "wife/husband/son/mother/boss")
- `services/search/resolver.py`: term → facet match. Tiered:
  - Tier 1: exact/case-insensitive match against vocabulary
  - Tier 2: trigram fuzzy match
  - Tier 3 (only if Tier 1+2 yield 0 or >1 ambiguous): Haiku LLM call to parse term into structured filter
- Unit tests for each tier and the chip composition

### `D4-02` Search endpoint + chip-based UI (75 min)
- `POST /search` (FastAPI): takes term + current chips → returns resolved chip + filtered documents
- `services/search/query.py`: build SQL from chip list (AND of facets); for `content` facet, hybrid (BM25 via tsvector + vector similarity)
- Frontend: top bar search input + chips below; press Enter adds chip; backspace on empty input removes last chip
- Result grid reuses `DocumentGrid` component
- Empty-result state with "remove last chip" suggestion

### `D4-03` Single-document chat (60 min)
- `POST /chat` (FastAPI, SSE) — scope=document path
- `services/chat/retriever.py`: vector search within document's chunks (top 5)
- `services/chat/responder.py`: stream Claude response with citations as separate SSE events
- Frontend on `/document/[id]`: side panel chat
- Cite chunks via clickable badges that highlight in the preview

### `D4-04` Cross-document chat with KG grounding (60 min)
- `POST /chat` scope=all path
- Retriever: first try to resolve the question via KG (e.g., "what's my passport number" → fact lookup); fall back to hybrid retrieval
- Responder includes structured KG snippets in context, instructed to prefer them as authoritative
- Cites source documents in responses
- Frontend: `/chat` page with thread list (single thread per user is fine for Phase 1)

### `D4-05` End-to-end integration smoke test (30 min)
- Spawn fresh user
- Upload 5 mixed-type docs (set aside as fixtures)
- Verify all reach `ready`
- Verify search chips work
- Verify graph populates
- Verify both chat modes respond accurately
- File any defects as PROGRESS.md tasks for Day 5

End-of-day-4 check: full demo path is functional. UI may still be rough.

---

## Day 5 — Polish + Demo (~5 hours)

Sequential. No new features unless trivially small.

### `D5-01` Pipeline animation polish (45 min)
- Refine the 5-stage live indicator on document cards and detail page
- Add micro-animations: a tick when each stage completes, color the badge
- Spinner with stage name on the active stage

### `D5-02` Tracing UI (30 min)
- Add a "View trace" link on document detail page → deep-links to Langfuse trace
- For local dev, use the env-specific Langfuse URL

### `D5-03` Empty states + onboarding (45 min)
- First-time user lands on `/`: empty state with copy and a sample-document upload hint
- Empty search results state
- Empty chat thread state ("Ask anything about your documents")
- Tooltips on key UI elements

### `D5-04` Mobile-responsive review (45 min)
- Make grid, search, and chat usable on phone (≥ 360px)
- Test on a real device

### `D5-05` Error states + retry (30 min)
- For docs in `failed` status: show error reason and a "Retry" button that re-enqueues
- API error toasts with helpful messages

### `D5-06` Demo seeding (60 min)
- Prepare a demo user with 8–10 pre-uploaded varied documents (covering the demo flow in `01-OVERVIEW.md`)
- Record a 3-minute Loom demo against this account
- Save the demo account credentials in PROGRESS.md (for reset before any live demo)

### `D5-07` Final sweep (30 min)
- Run all tests
- Re-read PROGRESS.md and KNOWLEDGE.md for stale items
- Update KNOWLEDGE.md with the "final state" summary
- Tag git: `v1.0-phase-1`

End-of-day-5 check: demo recorded; production deployed; PROGRESS.md shows all tasks closed.

---

## Buffer policy

If you fall behind:
- Cut: graph view (Day 3 FE-02) and mobile responsive polish (Day 5 D5-04). The demo can be done on desktop.
- Cut: cross-document chat (Day 4 D4-04). Keep single-doc chat.
- Don't cut: the 5-agent harness, search chips, or live pipeline animation. Those are the demo.

Add the cuts to a `PHASE-1.5.md` file you create as needed.
