# 00 — Rules (Phase 1.5)

These rules are absolute for Phase 1.5. Where they conflict with Phase 1's `/plan/00-RULES.md`, **this file wins**. Where this file is silent, Phase 1 rules still apply.

## Phase boundary discipline

- **Do not edit Phase 1 plan files** (`/plan/00-RULES.md` through `/plan/08-PARALLEL-TRACKS.md`, `/plan/PROGRESS.md`, `/plan/KNOWLEDGE.md`). They are frozen historical record. If you spot an error in Phase 1 docs, note it in `KNOWLEDGE-1.5.md` under "Phase 1 doc corrections" — never edit the source.
- **Phase 1.5 files live in `/plan/phase-1.5/`**. Any new doc goes here.
- **Tag boundary:** `v1.0-phase-1` marks the end of Phase 1. At the end of Phase 1.5, tag `v1.1-phase-1.5`. Do not move existing tags.

## Session protocol

### At session start (always)
1. Read `/plan/phase-1.5/00-RULES-1.5.md` (this file)
2. Read `/plan/phase-1.5/PROGRESS-1.5.md` — find the current open task and the "Up Next" queue
3. Read `/plan/phase-1.5/KNOWLEDGE-1.5.md` — load current 1.5 state, decisions, gotchas
4. Skim `/plan/KNOWLEDGE.md` (Phase 1 record) — context only
5. Read `/plan/05-CODING-STANDARDS.md` — code conventions (unchanged from Phase 1)
6. Read the specific 1.5 plan file relevant to the task

### During session
- Make small, verifiable commits. One logical change per commit.
- **Commit format:** Conventional Commits with explicit phase scope when the change is Phase 1.5 work.
  - `feat(pipeline,phase-1.5): make agent stages concurrent within document`
  - `fix(verifier,phase-1.5): increment retry_count only on actual retry`
  - `refactor(agents,phase-1.5): remove module-level agent singletons`
  - `perf(search,phase-1.5): cache vocab per user with TTL`
  - `test(harness,phase-1.5): add groundedness check unit tests`
- **No co-author lines.** Do not add "Co-Authored-By: Claude" or any AI attribution.
- When a decision needs to be made that wasn't in the docs, **pause and ask** rather than guessing.
- Run linters, formatters, and the relevant tests before committing.
- Never leave broken code in `main`. Use feature branches.

### Git rules (CRITICAL — never violate)
1. **NEVER run git commands directly.** Only output the commands for the user to run. The user executes all git operations.
2. **Diff before commit commands.** Before suggesting any commit commands, always run `git status` and `git diff --stat` to see the actual uncommitted changes. Build commit commands based on the real diff — never from memory.
3. **Update PROGRESS-1.5.md BEFORE outputting commit commands.** When a task completes, first: (a) mark it `[x]` with `YYYY-MM-DD HH:MM` in both the "Phase 1.5 task tracker" table AND "Recently completed"; (b) move "Current" to the next task in the queue; (c) mark any resolved defect `[x]` in the "Defects tracker" section. Only then output git commit commands.
4. **Checkpoint & pause.** After updating PROGRESS-1.5.md and outputting git commands, **STOP. Do not continue to the next task.** Wait for the user to confirm they have run the commands.
5. **Verify after commit.** After the user confirms, run `git log --oneline -n <count>` and `git status` to verify everything was committed properly. Only then proceed to the next task.

### At session end (always)
1. Update `PROGRESS-1.5.md`:
   - Mark completed tasks with `[x]` and timestamp in the "Phase 1.5 task tracker" table
   - Add completed tasks to "Recently completed" list (last 10; prune oldest to `KNOWLEDGE-1.5.md`)
   - Move next task to "Current"
   - Update "Defects tracker" — mark any closed defects `[x]`
   - Add any new blockers under "Blockers"
   - Append one-liner to "Session log": `YYYY-MM-DD HH:MM | track | session description | tasks closed | next up`
2. If a milestone or day completes, update `KNOWLEDGE-1.5.md`:
   - New decisions made (with reasoning)
   - New gotchas discovered
   - Updated performance numbers
   - Updated test fixture list
   - Update "Phase 1.5 current state" summary
   - Update "Agents and services added" and "API endpoints added or changed" if applicable
3. Commit doc updates separately from code: `docs(progress,phase-1.5): close <task-id>`

## Branching strategy

- Single-session work: branch `phase-1.5/<task-id>` (e.g., `phase-1.5/P1-PARA-01`)
- Parallel tracks (see `08-PARALLEL-TRACKS-1.5.md`): branch `phase-1.5/<track>/<task-id>` (e.g., `phase-1.5/track-a/P1-PARA-01`)
- Merge to `main` via fast-forward when there is one track, or via merge commit when multiple tracks merge in a single integration session
- **Never push directly to `main`.** Always go through a branch.

## Tagging at end of phase

When `PROGRESS-1.5.md` shows all tasks complete and the integration smoke passes:
```
git checkout main
git pull
git tag -a v1.1-phase-1.5 -m "Phase 1.5 — Optimization, self-healing, hybrid chat"
git push origin v1.1-phase-1.5
```

## Coding rules (additions to Phase 1)

The following rules are **new in Phase 1.5** or **strengthened** versions of Phase 1 rules.

### Concurrency safety
- **No module-level mutable state** in any agent or service module. If an agent or service has any `self._foo = ...` that holds per-request data, the class must be instantiated per request, not as a module singleton.
- **No request-scoped data on shared instances.** Per-document state (page images, intermediate outputs) is passed as function arguments, returned, or stored in DB — never on a long-lived object.
- **All concurrent work uses `asyncio.gather` with explicit error handling.** No fire-and-forget tasks unless they're explicitly background and cancellable.
- **Idempotency by default.** Any operation that can be retried (job, agent call, DB write) must be idempotent or have a deduplication key.

### Measurement before optimization
- Before claiming a perf improvement, capture **before** and **after** numbers. Both go into the PR description and `KNOWLEDGE-1.5.md` under "Performance log."
- Every hot path has a structured log line with `duration_ms`. Add one if missing.
- Optimizations without measurement are not accepted into `main`.

### Tests are required for Phase 1.5
- Phase 1 shipped with zero tests (per state report). Phase 1.5 ships with tests for **every new behavior**:
  - Unit test per new agent behavior (mocked LLM)
  - Integration test per modified pipeline stage
  - Regression test for every fixed defect (proves the bug is gone and doesn't return)
- A defect listed in `02-DEFECT-LEDGER.md` is not "closed" until a regression test exists.

### LLM API retry policy
- All LLM API calls (Anthropic, OpenAI) get retry with exponential backoff (max 3 attempts, base 1s, cap 8s) on **transient** errors only: 429, 500, 502, 503, 504, connection errors. Implemented once in `integrations/anthropic_client.py` and `integrations/openai_embeddings.py`, not per agent.
- Permanent errors (400 bad request, schema validation) **do not retry**.

### Hallucination guardrails
- Every extracted field's `value` is checked against `raw_text` (substring/normalized substring) before the field is persisted. Result stored in `extracted_fields.is_grounded` (new column). If not grounded, confidence is capped and the field is flagged for retry.
- Cross-document chat responses cite both KG facts (by entity + field name) and chunks (by chunk_id). Responder may not emit unsourced claims.

### Data privacy logging
- Continue Phase 1's discipline: never log raw document content. Add: do not log full extracted field values for fields marked sensitive (PAN, Aadhaar, passport_number, account numbers). Log field name only.

## Forbidden actions

- ❌ Don't edit any file under `/plan/*.md` (Phase 1 root files).
- ❌ Don't disable the new groundedness check to "make tests pass."
- ❌ Don't introduce a new module-level singleton for any object that holds per-document or per-user state.
- ❌ Don't expand scope (no new product features in Phase 1.5).
- ❌ Don't skip the regression test when fixing a ledger defect.
- ❌ Don't merge a track branch without updating `PROGRESS-1.5.md` first.

## When stuck

Same as Phase 1:
1. Add a `BLOCKER` entry to `PROGRESS-1.5.md` with the question
2. Skip to the next non-dependent task if one exists
3. Don't guess — surface the question to the human

## Quality bar at end of Phase 1.5

The phase is done only when ALL of these hold:
- All tasks in `PROGRESS-1.5.md` are `[x]`
- Every defect in `02-DEFECT-LEDGER.md` is closed with a regression test
- Performance targets in `06-PERFORMANCE-TARGETS.md` are met for the demo corpus
- `pytest -q` in `/api` passes 100%
- `pnpm test` and `pnpm typecheck` pass 100% in `/web`
- A clean end-to-end smoke test (upload 10 mixed-type docs, verify all reach `ready`, run hybrid chat, run search) passes on a fresh user
- Tag `v1.1-phase-1.5` is pushed
