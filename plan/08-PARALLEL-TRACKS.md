# 08 — Parallel Tracks

This file describes how to run multiple Claude Code sessions in parallel to compress the 5-day schedule, and how to merge their work.

## Core principle

Parallel sessions are valuable only if their work doesn't conflict. The boundaries that make this safe:

- **API contracts** in `03-ARCHITECTURE.md` are **frozen** at end of Day 1. Parallel tracks build against the contract; they don't change it.
- **Data model** is frozen end of Day 1 (only additive changes allowed in parallel — and only by the Backend track).
- **Folder boundaries**: each track owns specific folders. Cross-folder edits require coordination.

## Track ownership map

| Folder / file | Track owner | Can other tracks edit? |
|---|---|---|
| `web/` (except types) | Frontend | No |
| `web/lib/types/` | Both (auto-generated from backend schemas) | Read-only for Frontend |
| `api/app/agents/` | Agent | No |
| `api/app/services/pipeline/` | Agent | No |
| `api/app/parsing/` | Agent | No |
| `api/app/routes/`, `api/app/services/` (other) | Backend | No |
| `api/app/repositories/` | Backend | No |
| `api/migrations/` | Backend | No |
| `plan/` | All sessions (only PROGRESS.md + KNOWLEDGE.md) | Yes for living files; no for plan files |

## Track definitions

### Track A — Backend Core
Owns: `api/app/routes/`, `api/app/services/` (except `pipeline/`), `api/app/repositories/`, `api/migrations/`, `api/app/integrations/`, `api/app/db/`.

Phase 1 tasks (in order):
- `D2-BE-01` Document upload endpoint
- `D2-BE-04` Pipeline state machine (skeleton — does not call agents yet, just transitions status)
- `D4-01` Search resolver
- `D4-02` Search endpoint
- `D4-03` Single-doc chat
- `D4-04` Cross-doc chat with KG retrieval

### Track B — Frontend
Owns: `web/` (everything).

Phase 1 tasks (in order):
- `D2-FE-01` App shell + library page
- `D2-FE-02` Upload widget
- `D2-FE-03` Document grid with Realtime
- `D3-FE-01` Document detail page
- `D3-FE-02` Graph view
- Search UI integration (chips, results)
- Chat UI integration (single doc + cross-doc)

### Track C — Agent Harness
Owns: `api/app/agents/`, `api/app/services/pipeline/`, `api/app/parsing/`, `api/app/worker/`, fixture documents.

Phase 1 tasks (in order):
- `D2-BE-02` File-type parsers
- `D2-BE-03` Classifier agent
- `D3-BE-01` Schema architect + Extractor
- `D3-BE-02` Verifier + retry
- `D3-BE-03` Knowledge Integrator + entity resolution
- `D3-BE-04` Vectorization

## Schedule with parallelism

### Day 1 — Sequential (single session)
All foundation tasks (`D1-01` through `D1-07`). No parallelism possible. ~5 hours.

**Day 1 lockdown:** at end of Day 1, freeze `03-ARCHITECTURE.md` API contracts and `04-DATA-MODEL.md` schema. Commit the lockdown explicitly: `chore(plan): freeze API contracts and schema for parallel work`.

### Day 2 — Two parallel sessions
| Session | Work |
|---|---|
| Track A (Backend) | `D2-BE-01` Document upload endpoint, `D2-BE-04` Pipeline state machine skeleton |
| Track C (Agent) | `D2-BE-02` File parsers, `D2-BE-03` Classifier agent |
| Track B (Frontend) | `D2-FE-01`, `D2-FE-02`, `D2-FE-03` (can run as a 3rd parallel session OR be done by you between A/C check-ins) |

Tracks A and C touch different folders. Track B is fully in `web/`. Three sessions can run in parallel safely.

End of Day 2 merge step: Track A and Track C both modify `pipeline/orchestrator.py` if they go fast (Track A adds the state machine skeleton; Track C plugs in the classifier as the first agent stage). To avoid conflict: **Track A finishes its orchestrator skeleton first; Track C extends it.** Coordinate via PROGRESS.md status `D2-BE-04 done`.

### Day 3 — Two parallel sessions
| Session | Work |
|---|---|
| Track C (Agent) | `D3-BE-01` Schema + Extractor, `D3-BE-02` Verifier, `D3-BE-03` Integrator, `D3-BE-04` Vectorization |
| Track B (Frontend) | `D3-FE-01` Document detail, `D3-FE-02` Graph view |

Track A is idle on Day 3 — its work is done; the next thing it does is Day 4 search/chat. Use Track A's session slot to either help Track C with `services/knowledge/` (still Track C territory but adjacent) OR start Day 4 `D4-01` search resolver early.

End of Day 3 merge step: pull and resolve any merges in `pipeline/orchestrator.py`. Run integration test.

### Day 4 — Two parallel sessions
| Session | Work |
|---|---|
| Track A (Backend) | `D4-01` resolver, `D4-02` search endpoint, `D4-03` single-doc chat, `D4-04` cross-doc chat |
| Track B (Frontend) | Search UI (chips + results), Chat UI (single + cross) |

End of Day 4 — Required sequential merge step `D4-05`:
- All tracks merged to main
- One session runs the end-to-end smoke test (single Claude Code session, sequential)
- File defects as Day 5 tasks

### Day 5 — Sequential single session
Polish and demo. No parallelism.

## How to run parallel sessions practically

Three options, choose based on tooling:

**Option 1: Multiple Claude Code instances with branches** (recommended)
- Create a branch per track: `track/a-backend`, `track/b-frontend`, `track/c-agent`
- Each Claude Code session checked out on its branch
- PROGRESS.md updated on the branch; merged to main at end-of-day
- Conflicts resolved during the end-of-day merge step

**Option 2: Worktree-per-track**
- `git worktree add ../brain-track-a track/a-backend`
- Each track gets a physical folder; no branch switching needed
- Each Claude Code session points at its own worktree

**Option 3: Sequential with daily checkpoints**
- Drop parallelism. Run sessions back-to-back.
- Slower but no merge conflicts.

If new to multi-session work, use Option 1 with end-of-day merges. Option 2 is best for power users.

## Merge protocol (end of day)

When merging multiple tracks:

1. Each track's session ends by:
   - Pushing its branch
   - Updating PROGRESS.md with all completed task IDs
   - Listing any uncommitted scratch in `KNOWLEDGE.md` under "In-flight"

2. A single merge session does:
   - `git fetch --all`
   - For each branch: `git merge track/X --no-ff` into `main`
   - Resolve conflicts. PROGRESS.md and KNOWLEDGE.md conflicts: take the union (additive).
   - Run all tests: `pytest` and `pnpm test`
   - Run lint/format/type checks
   - Manually do the integration smoke from `07-EXECUTION-PLAN.md` end-of-day check
   - Commit: `chore(merge): day-N merge of tracks A/B/C`
   - Update KNOWLEDGE.md with any cross-cutting decisions made during merge
   - Push main

3. Each track's next-day session starts by:
   - `git checkout main && git pull`
   - `git checkout -b track/X-day-N+1`
   - Reading the merged PROGRESS.md to pick up the next task

## Conflict-avoidance rules

- **Never edit another track's folders.** If you need a function in another track's code, file a `BLOCKER` in PROGRESS.md.
- **Never edit migrations except via Track A.** If you need a schema change in Track C, file a request.
- **Always pull PROGRESS.md before writing to it.** It's the most-touched file.
- **The plan/ files (other than PROGRESS and KNOWLEDGE) are append-only during execution.** If you find a mistake, surface it in KNOWLEDGE.md under "Plan corrections" and only the human edits the source plan file.

## Integration test (required after every merge)

```bash
# /api
pytest -q
ruff check . && mypy app/

# /web
pnpm test && pnpm typecheck && pnpm lint

# E2E
# 1. spin up local docker compose (redis + langfuse)
# 2. start api: uvicorn app.main:app
# 3. start worker: arq app.worker.WorkerSettings
# 4. start web: pnpm dev
# 5. log in as test user, upload fixture PDF, wait for `ready` status, run a search, run a chat
```

If any step fails, no further development on `main` until the merge session resolves.

## Communication between sessions (without a human)

Sessions cannot talk to each other directly. They coordinate via:
- **Git**: branches and merge timing
- **PROGRESS.md**: task state ("D2-BE-04 done" signals Track C may proceed)
- **KNOWLEDGE.md**: decisions and gotchas (e.g., "OpenAI embedding dim is 1536; bumped vector column type")

A session that needs information another session has should NOT guess. It writes a BLOCKER in PROGRESS.md and skips to a non-blocked task.

## Recommended human cadence

If running parallel sessions:
- Mid-morning: kick off all tracks for the day, each on its branch
- Lunch: 10-minute check, read PROGRESS.md, unblock any BLOCKERs
- Evening: run the merge session
- End of day: tag a commit with `day-N-end` for easy rollback
