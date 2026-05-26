# Phase 1.5 — Optimization, Self-Healing, Hybrid Chat

Phase 1 shipped a working harness. Phase 1.5 makes it **fast**, **trustworthy**, and **smart** — without expanding scope. No new product features, no financial domain yet. Just: tighten everything we already built.

## What changed since Phase 1

This phase began after Phase 1 was tagged `v1.0-phase-1`. Phase 1 files in `/plan/` (`00-RULES.md` through `08-PARALLEL-TRACKS.md`, `PROGRESS.md`, `KNOWLEDGE.md`) are **frozen as historical record**. Do not edit them.

Phase 1.5 files live in **this folder** (`/plan/phase-1.5/`). The two living files (`PROGRESS-1.5.md` and `KNOWLEDGE-1.5.md`) carry forward from Phase 1's `PROGRESS.md` and `KNOWLEDGE.md` patterns but are scoped to 1.5.

## File index (read order)

| # | File | Purpose | When to read |
|---|------|---------|-------------|
| 0 | `00-RULES-1.5.md` | Non-negotiables, supersedes some Phase 1 rules | Every session, start |
| 1 | `01-OBJECTIVES.md` | What Phase 1.5 fixes and why — read once | Once, at start |
| 2 | `02-DEFECT-LEDGER.md` | Concrete bugs + gaps to fix, with file:line refs | Reference during task work |
| 3 | `03-PARALLELISM-DESIGN.md` | How the pipeline becomes concurrent + safe | When working on pipeline |
| 4 | `04-SELF-HEALING-HARNESS.md` | Adaptive retry, groundedness, hallucination control | When working on agents/verifier |
| 5 | `05-HYBRID-CHAT.md` | KG + vector fusion, history, citations | When working on chat |
| 6 | `06-PERFORMANCE-TARGETS.md` | SLOs, measurement, regression bar | Every session that touches hot paths |
| 7 | `07-EXECUTION-PLAN-1.5.md` | Day-by-day task plan (5 days) | Every session |
| 8 | `08-PARALLEL-TRACKS-1.5.md` | Multi-session orchestration for 1.5 | When running parallel sessions |
| L1 | `PROGRESS-1.5.md` | Living checklist | Every session, start AND end |
| L2 | `KNOWLEDGE-1.5.md` | Living state | Every session, start AND end of phase |

## Quick start for any Claude Code session

```
1. Read /plan/phase-1.5/00-RULES-1.5.md
2. Read /plan/phase-1.5/PROGRESS-1.5.md  (find current task)
3. Read /plan/phase-1.5/KNOWLEDGE-1.5.md (load 1.5-specific decisions)
4. Read /plan/KNOWLEDGE.md (Phase 1 history; treat as read-only)
5. Read /plan/05-CODING-STANDARDS.md (still authoritative for code conventions)
6. Read the specific 1.5 plan file relevant to current task
7. Execute task
8. Update PROGRESS-1.5.md (mark done, set next)
9. If phase milestone complete: update KNOWLEDGE-1.5.md
```

## Phase 1 docs that still apply unchanged

- `/plan/05-CODING-STANDARDS.md` — folder structure and coding patterns. Phase 1.5 follows the same conventions.
- `/plan/04-DATA-MODEL.md` — the schema is mostly preserved. Phase 1.5 adds **migrations** for new tables/columns but doesn't change existing ones unless `02-DEFECT-LEDGER.md` says so.
- `/plan/03-ARCHITECTURE.md` — service boundaries are unchanged. Only **internals** of services change.

## Phase 1 docs that are partially superseded

- `/plan/00-RULES.md` — see `00-RULES-1.5.md` for additions and the few overrides.
- `/plan/06-AGENT-HARNESS.md` — the agent contracts are the same, but the **retry policy** and **verifier behavior** change. See `04-SELF-HEALING-HARNESS.md`.

## Tagging and branching

- Phase 1.5 work happens on branches `phase-1.5/<track>/<task-id>`
- All merges go to `main`
- End of Phase 1.5: tag `v1.1-phase-1.5`
- All commits use Conventional Commits with a `phase-1.5` scope tag where appropriate, e.g. `feat(pipeline,phase-1.5): parallelize text extraction with classifier prefetch`

See `00-RULES-1.5.md` for full commit/tag rules.
