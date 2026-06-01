# Phase: Notes + Entity Dedupe — Plan Index

**Branch:** `phase-notes-dedupe/main`
**End tag:** `v1.2-phase-notes-dedupe`
**Builds on:** Phase 1.5 (`v1.1-phase-1.5`)

---

## What this phase delivers

1. **User notes as first-class signals** — notes captured at upload and on the document detail page flow into the knowledge graph (entity resolution, vectorization, chat retrieval, `@mention` entity linking).
2. **Entity deduplication** — prevention (better matching + richer KI context + `uncertain` signal preservation), detection (background sweep), merge (API + minimal UI with explicit fact-conflict semantics), and backfill (one-time sweep on existing graph with safety rails).

---

## Read order at session start

Always read in this order before touching code:

| Order | File | Purpose |
|---|---|---|
| 1 | `00-RULES.md` | Absolute rules; commit format; git discipline |
| 2 | `PROGRESS.md` | Current task, Up Next queue, blockers |
| 3 | `KNOWLEDGE.md` | Decisions, gotchas, performance numbers |
| 4 | `00-DISCOVERY.md` | Codebase state at phase start — read once, refer back |
| 5 | `/plan/phase-1.5/KNOWLEDGE-1.5.md` | Phase 1.5 record (context only) |
| 6 | `/plan/05-CODING-STANDARDS.md` | Code conventions (unchanged) |
| 7 | Task-specific plan file (02 or 03) | Design for current work |

---

## Plan files

| File | Contents |
|---|---|
| `00-RULES.md` | Phase rules — session protocol, git rules, coding rules, forbidden actions |
| `00-DISCOVERY.md` | Pre-plan codebase analysis — read before planning or implementing |
| `01-OBJECTIVES.md` | Goals, success criteria, demo moments |
| `02-NOTES-DESIGN.md` | Full design for user notes feature |
| `03-ENTITY-DEDUPE-DESIGN.md` | Full design for entity deduplication |
| `04-EXECUTION-PLAN.md` | Task IDs, phases A–H, file lists, verification steps |
| `05-PARALLEL-TRACKS.md` | How to split into concurrent sessions; integrator prompt contract |
| `PROGRESS.md` | Living task tracker — update frequently |
| `KNOWLEDGE.md` | Living decisions/gotchas log — update at milestones |

---

## Phase structure

```
Phase A — Notes capture + storage (DB, API, frontend)
Phase B — Notes integrated into harness (vectorizer, integrator context)
Phase C — Notes mention parsing + entity linking (@mention, #tag)
Phase D — Dedupe prevention (better candidate matching + richer KI context + uncertain signal preservation)
Phase E — Dedupe detection (sweep + entity_duplicate_candidates table)
Phase F — Dedupe merge (API + minimal UI + fact-conflict semantics)
Phase G — Backfill on existing graph (notes + dedupe, with safety rails)
Phase H — End-to-end smoke + tracing audit + final benchmark
```

Track A (notes) = Phases A, B, C
Track B (dedupe) = Phases D, E, F
Sequential: Phase G backfill + Phase H smoke

---

## Key constraints

- Do NOT edit files under `/plan/*.md` or `/plan/phase-1.5/`. Those are frozen.
- Commit scope: `phase-notes-dedupe`
- Branch prefix: `phase-notes-dedupe/`
- Notes re-processing after edit must use a targeted path — not the full pipeline re-run.
- The integrator prompt is touched by both tracks — changes must be coordinated per `05-PARALLEL-TRACKS.md`.
- `@mention` resolution MUST go through `entity_resolver.resolve_and_persist()` to preserve dedupe protections.
- All `FROM entities` reads MUST filter `deleted_at IS NULL` (audit task ND-D-05).
