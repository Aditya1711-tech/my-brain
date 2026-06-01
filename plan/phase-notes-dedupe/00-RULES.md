# 00 — Rules (Phase: Notes + Entity Dedupe)

These rules are absolute for this phase. Where they conflict with Phase 1.5's `/plan/phase-1.5/00-RULES-1.5.md`, **this file wins**. Where this file is silent, Phase 1.5 rules still apply.

## Phase boundary discipline

- **Do not edit Phase 1 or Phase 1.5 plan files.** `/plan/00-RULES.md` through `/plan/08-PARALLEL-TRACKS.md`, `/plan/PROGRESS.md`, `/plan/KNOWLEDGE.md`, and all files under `/plan/phase-1.5/` are frozen historical record. If you spot an error in prior docs, note it in `KNOWLEDGE.md` (this phase's file) under "Prior phase doc corrections" — never edit the source.
- **This phase's files live in `/plan/phase-notes-dedupe/`**. Any new doc goes here.
- **Tag boundary:** `v1.1-phase-1.5` marks the end of Phase 1.5. At the end of this phase, tag `v1.2-phase-notes-dedupe`. Do not move existing tags.

## Session protocol

### At session start (always)
1. Read `/plan/phase-notes-dedupe/00-RULES.md` (this file)
2. Read `/plan/phase-notes-dedupe/PROGRESS.md` — find the current open task and the "Up Next" queue
3. Read `/plan/phase-notes-dedupe/KNOWLEDGE.md` — load current state, decisions, gotchas
4. Skim `/plan/phase-1.5/KNOWLEDGE-1.5.md` (Phase 1.5 record) — context only
5. Read `/plan/05-CODING-STANDARDS.md` — code conventions (unchanged from Phase 1)
6. Read the specific plan file relevant to the task (02-NOTES-DESIGN.md or 03-ENTITY-DEDUPE-DESIGN.md)

### During session
- Make small, verifiable commits. One logical change per commit.
- **Commit format:** Conventional Commits with explicit phase scope.
  - `feat(notes,phase-notes-dedupe): add user_note textarea to upload dropzone`
  - `feat(integrator,phase-notes-dedupe): pass note context to KI input`
  - `fix(dedupe,phase-notes-dedupe): increase trigram threshold to 0.5`
  - `test(notes,phase-notes-dedupe): add note mention parsing unit tests`
  - `docs(progress,phase-notes-dedupe): close ND-A-01`
- **No co-author lines.** Do not add "Co-Authored-By: Claude" or any AI attribution.
- When a decision needs to be made that wasn't in the docs, **pause and ask** rather than guessing.
- Run linters, formatters, and the relevant tests before committing.
- Never leave broken code in `main`. Use feature branches with prefix `phase-notes-dedupe/`.

### Git rules (CRITICAL — never violate)
1. **NEVER run git commands directly.** Only output the commands for the user to run. The user executes all git operations.
2. **Diff before commit commands.** Before suggesting any commit commands, always run `git status` and `git diff --stat` to see the actual uncommitted changes. Build commit commands based on the real diff — never from memory.
3. **Update PROGRESS.md BEFORE outputting commit commands.** When a task completes, first: (a) mark it `[x]` with `YYYY-MM-DD HH:MM` in both the "task tracker" table AND "Recently completed"; (b) move "Current" to the next task in the queue; (c) mark any resolved defect `[x]` in the "Defects tracker" section. Only then output git commit commands.
4. **Checkpoint & pause.** After updating PROGRESS.md and outputting git commands, **STOP. Do not continue to the next task.** Wait for the user to confirm they have run the commands.
5. **Verify after commit.** After the user confirms, run `git log --oneline -n <count>` and `git status` to verify everything was committed properly. Only then proceed to the next task.

### At session end (always)
1. Update `PROGRESS.md`:
   - Mark completed tasks with `[x]` and timestamp in the task tracker table
   - Add completed tasks to "Recently completed" list (last 10; prune oldest to `KNOWLEDGE.md`)
   - Move next task to "Current"
   - Update "Defects tracker" — mark any closed defects `[x]`
   - Add any new blockers under "Blockers"
   - Append one-liner to "Session log": `YYYY-MM-DD HH:MM | track | session description | tasks closed | next up`
2. If a milestone or track completes, update `KNOWLEDGE.md`:
   - New decisions made (with reasoning)
   - New gotchas discovered
   - Updated performance numbers
   - Updated test fixture list
   - Update "Current state" summary
   - Update "Agents and services added" and "API endpoints added or changed" if applicable
3. Commit doc updates separately from code: `docs(progress,phase-notes-dedupe): close <task-id>`

## Branching strategy

- Single-session work: branch `phase-notes-dedupe/<task-id>` (e.g., `phase-notes-dedupe/ND-A-01`)
- Parallel tracks (see `05-PARALLEL-TRACKS.md`): branch `phase-notes-dedupe/<track>/<task-id>` (e.g., `phase-notes-dedupe/track-a/ND-A-01`)
- Merge to `main` via fast-forward when there is one active track, or via merge commit when multiple tracks merge in a single integration session
- **Never push directly to `main`.** Always go through a branch.

## Tagging at end of phase

When `PROGRESS.md` shows all tasks complete and the integration smoke passes:
```
git checkout main
git pull
git tag -a v1.2-phase-notes-dedupe -m "Phase notes+dedupe — user notes as first-class signals and entity deduplication"
git push origin v1.2-phase-notes-dedupe
```

## Coding rules (carry-over from Phase 1.5, unchanged)

### Concurrency safety
- **No module-level mutable state** in any agent or service module. If an agent or service has any `self._foo = ...` that holds per-request data, the class must be instantiated per request, not as a module singleton.
- **No request-scoped data on shared instances.** Per-document state is passed as function arguments, returned, or stored in DB — never on a long-lived object.
- **All concurrent work uses `asyncio.gather` with explicit error handling.** No fire-and-forget tasks unless they're explicitly background and cancellable.
- **Idempotency by default.** Any operation that can be retried (job, agent call, DB write) must be idempotent or have a deduplication key.

### Measurement before optimization
- Before claiming a perf improvement, capture **before** and **after** numbers. Both go into the PR description and `KNOWLEDGE.md` under "Performance log."
- Every hot path has a structured log line with `duration_ms`. Add one if missing.
- Optimizations without measurement are not accepted into `main`.

### Tests are required
- Unit test per new agent behavior (mocked LLM)
- Integration test per modified pipeline stage
- Regression test for every fixed defect
- A defect is not "closed" until a regression test exists

### LLM API retry policy (reuse Phase 1.5 implementation)
- All LLM API calls get retry with exponential backoff (max 3 attempts, base 1s, cap 8s) on transient errors: 429, 500, 502, 503, 504, connection errors. Already implemented in `integrations/anthropic_client.py` and `integrations/openai_embeddings.py`. Do NOT add per-call retry logic.
- Permanent errors (400, schema validation) **do not retry**.

### Hallucination guardrails
- Notes content when used in chat is subject to the same groundedness rules as extracted fields: the responder may not emit unsourced claims. Notes that contain `@mention` links to entities create structural citations — the note's document becomes a citable source for the entity mention.
- Cross-document chat responses cite both KG facts (by entity + field name) and chunks (by chunk_id). Responder may not emit unsourced claims.

### Data privacy logging
- Continue Phase 1.5's discipline: never log raw document content. Do not log full user note content — log note length and mention count only.
- Do not log full extracted field values for fields marked sensitive (PAN, Aadhaar, passport_number, account numbers). Log field name only.

## Forbidden actions

- ❌ Don't edit any file under `/plan/*.md` (Phase 1 root) or `/plan/phase-1.5/` (Phase 1.5 files).
- ❌ Don't disable the groundedness check.
- ❌ Don't introduce a new module-level singleton for any object that holds per-document or per-user state.
- ❌ Don't expand scope beyond notes-as-signals and entity-dedupe.
- ❌ Don't skip the regression test when fixing a ledger defect.
- ❌ Don't merge a track branch without updating `PROGRESS.md` first.
- ❌ Don't run the full document pipeline just to re-process a note edit — use the targeted note re-integration path.
- ❌ Don't bypass `entity_resolver.resolve_and_persist()` when creating entities from `@mention` confirmations — same dedupe protections must apply.
- ❌ Don't add a SELECT on `entities` anywhere without `AND deleted_at IS NULL` — merged entities must stay invisible to reads.

## When stuck

1. Add a `BLOCKER` entry to `PROGRESS.md` with the question
2. Skip to the next non-dependent task if one exists
3. Don't guess — surface the question to the human

## Quality bar at end of phase

The phase is done only when ALL of these hold:
- All tasks in `PROGRESS.md` are `[x]`
- Performance targets in `04-EXECUTION-PLAN.md` are met for the demo corpus
- `pytest -q` in `/api` passes 100%
- `pnpm test` and `pnpm typecheck` pass 100% in `/web`
- End-to-end smoke: upload 5 docs with notes, verify notes influence entity resolution, verify notes surface in chat, verify deduplication sweep finds and merges known duplicate pair
- Tracing audit (ND-H-04) confirms the four required spans exist for the new paths
- Tag `v1.2-phase-notes-dedupe` is pushed
