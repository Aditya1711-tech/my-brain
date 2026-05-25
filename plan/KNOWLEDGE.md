# KNOWLEDGE — Living project state

Update after each phase completes or any non-trivial decision is made. Resume sessions should be able to read this and load the full project context.

---

## Current state

> What's deployed, what's working, what's mocked.

- **Full pipeline**: All 5 agents (Classifier, Schema Architect, Extractor, Verifier, Knowledge Integrator) + vectorization step implemented
- **Search**: 3-tier resolver (exact, trigram fuzzy, Haiku LLM) + hybrid BM25/vector query
- **Chat**: Single-document and cross-document with SSE streaming, citations, KG grounding
- **Frontend**: Library with live pipeline animations, document detail with fields/entities/timeline/chat, search with chip UI, knowledge graph with force-directed layout, global chat page
- **Error handling**: Retry button on failed documents, error states throughout

## Architecture decisions

> Format: short title — date — decision — reasoning.

- Next.js 16 proxy — 2026-05-20 — `middleware.ts` renamed to `proxy.ts` per Next.js 16 breaking change. All async APIs (`cookies()`, `params`) must be awaited.
- Base UI dropdown — 2026-05-20 — shadcn/ui now uses `@base-ui/react` not Radix. No `asChild` prop; Trigger renders children directly.
- Langfuse init — 2026-05-20 — `Langfuse()` constructor no longer accepts `enabled` kwarg. Check for keys before init, set `.enabled` attribute after.
- SQL casts — 2026-05-21 — Use `CAST(:param AS jsonb)` and `CAST(:param AS vector)` instead of `::` syntax for asyncpg compatibility.
- Supabase storage — 2026-05-21 — Use `settings.supabase_storage_bucket` config instead of parsing storage_path for bucket name.

## Schema state

> What tables exist and what's been added since the initial migration.

- **Initial migration**: applied (0001 — all tables from 04-DATA-MODEL.md)
- **RLS migration**: applied (0002 — per-user policies on all tables)
- **Tables**: folders, tags, documents, document_tags, extracted_fields, entities, entity_relationships, facts, document_entities, chunks, document_pipeline_events
- **Pending changes**: none

## API endpoints implemented

> Append as endpoints land. Format: `METHOD /path — purpose — owner track`.

- `GET /health` — DB connectivity check — D1-04
- `POST /enqueue` — queue doc for processing (API-key protected) — D1-05
- `POST /search` — resolve term into chip + query documents — D4-01/D4-02
- `POST /chat` — SSE streaming chat with retrieval + KG grounding — D4-03/D4-04

## BFF routes (Next.js)

- `POST /api/documents` — create document record + enqueue — D2-BE-01
- `POST /api/documents/retry` — reset failed doc + re-enqueue — D5-05
- `POST /api/search` — proxy to FastAPI search — D4-02
- `POST /api/chat` — proxy SSE stream from FastAPI — D4-03

## Agents implemented

> Per `06-AGENT-HARNESS.md`. Tick when complete.

- [x] Classifier (Haiku 4.5)
- [x] Schema Architect (Sonnet 4.6)
- [x] Extractor (Sonnet 4.6, multimodal)
- [x] Verifier (Haiku 4.5) — with targeted retry (max 2)
- [x] Knowledge Integrator (Sonnet 4.6)
- [x] Vectorization (deterministic — OpenAI text-embedding-3-small)

## Frontend pages

- `/` — Library page with document grid, upload dropzone, live pipeline animations
- `/document/[id]` — Detail page with extracted fields, entities, pipeline timeline, chat panel, retry
- `/search` — Chip-based search with facet resolution
- `/chat` — Cross-document chat with KG grounding
- `/graph` — Knowledge graph visualization (react-force-graph-2d)
- `/login`, `/signup` — Auth pages

## Dependencies added beyond `02-TECH-STACK.md`

> Anything `pip install`ed or `pnpm add`ed that wasn't in the pinned list. Each needs a one-line justification.

- `python-dotenv` — needed for Alembic env.py to load .env from project root
- `pnpm` — not pre-installed on Windows; had to `npm i -g pnpm`
- `react-force-graph-2d` — force-directed graph visualization for /graph page

## Gotchas discovered

> Tribal knowledge. Things that took longer than they should have, or surprised you.

- asyncpg doesn't support `::type` cast syntax — must use `CAST(... AS type)`
- shadcn/ui Button uses Base UI, no `asChild` — use `<a>` directly instead of wrapping
- Supabase storage download needs bucket name from config, not parsed from storage_path
- Next.js 16 `params` and `searchParams` are Promises — must `await` them in page components

## Plan corrections

> If you find a mistake in the plan files, note it here.

_(none)_

## Test fixtures

> Sample documents used in tests. Path + what they're for.

_(none yet — D4-05 integration test deferred to deploy)_

## Demo account

> Credentials and setup for the Day 5 demo recording. Reset before any live demo.

- **Email**: TBD
- **Password**: TBD
- **Seeded documents**: TBD

## Cost telemetry

> Update as cost-per-document data accumulates.

- **Target**: ≤ $0.10/doc
- **Actual avg**: TBD
- **Actual max**: TBD

## Open questions

> Things to validate with the human before assuming.

_(none)_

## Phase 1.5 backlog

> Things cut from Phase 1 for time. Carry forward.

- D4-05: End-to-end integration smoke test (deferred to deploy)
- D5-04: Mobile-responsive review
- D5-06: Demo seeding + Loom recording
- Video and audio processing
- Smart-merge UI for ambiguous entities
- Re-run extraction at scale
- Edit-extracted-field with agent retry
- Real-OCR step in parser router (Phase 1 uses multimodal Sonnet directly for image-heavy PDFs)

## Phase 2 preview

> Don't build now. Note here as ideas accumulate so they're not lost.

- Financial document intelligence (CAS, salary, CC bills, insurance, MF statements)
- Net-worth and portfolio dashboards
- Tax position tracking
- Goal-based planning
- Proactive monthly digest agent

---

## Phase completion log

> One entry per phase/day completed. Date + 3-line summary.

- **Day 1** — 2026-05-20 — Repo bootstrap, Supabase setup, migrations, API/worker/web scaffolds, deploy targets.
- **Day 2** — 2026-05-20 — Document upload, parsers, classifier agent, pipeline state machine, app shell, upload widget, realtime grid.
- **Day 3** — 2026-05-21 — Schema Architect, Extractor, Verifier (with retry), Knowledge Integrator, vectorization, document detail page, graph view.
- **Day 4** — 2026-05-21 — Search resolver (3-tier), search endpoint + chip UI, single-doc chat, cross-doc chat with KG grounding.
- **Day 5** — 2026-05-21 — Pipeline animation polish, Langfuse trace link, empty states, error states + retry.
