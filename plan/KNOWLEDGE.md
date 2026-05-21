# KNOWLEDGE — Living project state

Update after each phase completes or any non-trivial decision is made. Resume sessions should be able to read this and load the full project context.

---

## Current state

> What's deployed, what's working, what's mocked.

- **Deployed**: Vercel (web) + Railway (API) — basic scaffold
- **Working locally**: FastAPI /health, Next.js auth (login/signup/sign-out), library page with upload dropzone
- **Mocked**: Pipeline stages after classification (stub in orchestrator)

## Architecture decisions

> Format: short title — date — decision — reasoning.

- Next.js 16 proxy — 2026-05-20 — `middleware.ts` renamed to `proxy.ts` per Next.js 16 breaking change. All async APIs (`cookies()`, `params`) must be awaited.
- Base UI dropdown — 2026-05-20 — shadcn/ui now uses `@base-ui/react` not Radix. No `asChild` prop; Trigger renders children directly.
- Langfuse init — 2026-05-20 — `Langfuse()` constructor no longer accepts `enabled` kwarg. Check for keys before init, set `.enabled` attribute after.

## Schema state

> What tables exist and what's been added since the initial migration.

- **Initial migration**: applied (0001 — all tables from 04-DATA-MODEL.md)
- **RLS migration**: applied (0002 — per-user policies on all tables)
- **Pending changes**: none

## API endpoints implemented

> Append as endpoints land. Format: `METHOD /path — purpose — owner track`.

- `GET /health` — DB connectivity check — D1-04
- `POST /enqueue` — queue doc for processing (API-key protected) — D1-05

## Agents implemented

> Per `06-AGENT-HARNESS.md`. Tick when complete.

- [x] Classifier
- [ ] Schema Architect
- [ ] Extractor
- [ ] Verifier
- [ ] Knowledge Integrator
- [ ] (deterministic) Vectorization

## Dependencies added beyond `02-TECH-STACK.md`

> Anything `pip install`ed or `pnpm add`ed that wasn't in the pinned list. Each needs a one-line justification.

- `python-dotenv` — needed for Alembic env.py to load .env from project root
- `pnpm` — not pre-installed on Windows; had to `npm i -g pnpm`

## Gotchas discovered

> Tribal knowledge. Things that took longer than they should have, or surprised you. Future sessions read this and avoid the same trap.

_(none yet)_

## Plan corrections

> If you find a mistake in the plan files (`00-RULES.md` through `08-PARALLEL-TRACKS.md`), note it here. The human reviews and edits the source file.

_(none yet)_

## Test fixtures

> Sample documents used in tests. Path + what they're for.

_(none yet)_

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

_(none yet)_

## Phase 1.5 backlog

> Things cut from Phase 1 for time. Carry forward.

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

> One entry per phase/day completed. Date + 3-line summary. Drives the README in main repo.

_(none yet)_
