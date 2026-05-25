# 08 — Parallel Tracks (Phase 1.5)

How to compress Phase 1.5 to 3-4 calendar days by running parallel Claude Code sessions.

## Tracks

| Track | Owns | Tasks |
|-------|------|-------|
| **A — Harness Core** | `api/app/agents/`, `api/app/services/pipeline/`, `api/app/parsing/`, `api/app/worker/`, `api/app/utils/retry.py`, `api/app/integrations/` | D1 HARNESS-01..03, D2 HARNESS-04..09, D3 HARNESS-10..13, D5 HARNESS-14 |
| **B — Chat + Auth** | `api/app/routes/chat.py`, `api/app/services/chat/`, `api/app/deps.py` JWT, chat-related schema | D4 CHAT-01..05, D4 AUTH-01 |
| **C — Frontend + BFF** | `web/` | D4 CHAT-06, D5 INTEG LOW-class BFF additions |
| **D — Search + Misc** | `api/app/services/search/`, `api/app/repositories/`, benchmark scripts | D3 SEARCH-01..02, D1 BENCH-01, D2-D5 BENCH-02..05 |

The orchestrator is shared territory in `api/app/services/pipeline/orchestrator.py`. **All tracks coordinate any orchestrator edits via PROGRESS-1.5.md.** Track A owns orchestrator changes; other tracks file requests for orchestrator additions.

## Day-by-day with parallelism

### Day 1 (sequential foundation, single session)

All Day 1 tasks run in one session. No parallelism. Day 1 ends with all tracks ready to fork.

End-of-Day-1: tag `phase-1.5-d1-end` on main. Push.

### Day 2 (two parallel sessions)

| Session | Branch | Tasks |
|---------|--------|-------|
| Track A | `phase-1.5/track-a/d2-harness` | All D2 HARNESS-04..09 (migration, groundedness, verifier schema, retry loop, vectorization tracing, verifier text expansion) |
| Track D | `phase-1.5/track-d/d2-misc` | D2 BENCH-02 setup + tests for groundedness in isolation (read-only from track A's WIP) |

Track A is heavy on Day 2. Track D is light. If you have only one session slot, run Track A only on Day 2.

End-of-Day-2: merge `phase-1.5/track-a/d2-harness` → main, run benchmark, tag `phase-1.5-d2-end`.

### Day 3 (three parallel sessions)

| Session | Branch | Tasks |
|---------|--------|-------|
| Track A | `phase-1.5/track-a/d3-parallel` | HARNESS-10..13 (summarizer, parallelism, resumability, semaphores) |
| Track D | `phase-1.5/track-d/d3-search` | SEARCH-01..02 (vocab cache, fuzzy match) |
| Track C | `phase-1.5/track-c/d3-prep` | Frontend prep: chat-thread UI scaffolding, citation badge components, ready to wire up Day 4 |

Track A and Track D touch different folders. Track C is fully frontend. Three sessions can run safely.

End-of-Day-3: merge all three, run benchmark, tag `phase-1.5-d3-end`. Critical milestone — pipeline is now fast.

### Day 4 (three parallel sessions)

| Session | Branch | Tasks |
|---------|--------|-------|
| Track B | `phase-1.5/track-b/d4-chat-backend` | CHAT-01..05 + AUTH-01 (schema, router, KG retriever, vector upgrade, fusion, responder, JWT) |
| Track C | `phase-1.5/track-c/d4-chat-frontend` | CHAT-06 (thread list, history loading, dual citations) |
| Track D | `phase-1.5/track-d/d4-eval` | BENCH-04 (chat quality eval scaffolding) |

Track B and Track C have a contract: the chat API surface defined in `05-HYBRID-CHAT.md` is frozen. Both tracks build to that contract.

End-of-Day-4: merge all three, run integration smoke + chat quality eval, tag `phase-1.5-d4-end`.

### Day 5 (sequential single session)

All polish, final benchmark, tag-out. No parallelism.

## Coordination rules

### Orchestrator changes
Track A is the only track that edits `services/pipeline/orchestrator.py`. If another track needs an orchestrator hook (e.g., Track B wants the orchestrator to emit a chat-thread-ready signal — unlikely, but as an example), the request goes to PROGRESS-1.5.md under "Cross-track requests" and Track A adds it.

### Schema migrations
Each track creates its own additive migrations. Migration ordering is by timestamp — concurrent migrations from different tracks merge cleanly as long as they don't touch the same table. If two tracks need to touch the same table, **Track A** wins (Track A owns infra), and the other track waits for the merge.

Tracks that need new tables:
- Track A: `documents.processing_state` (additive column), `extracted_fields.*` new columns
- Track B: `chat_threads`, `chat_messages` (new tables)

No conflicts here.

### Shared utilities
`api/app/utils/` is shared. The only Phase 1.5 addition is `retry.py` (Track A). Other tracks may add small utilities; coordinate via PROGRESS-1.5.md.

### Test scaffolding
Tests live in `api/tests/`. Each track adds tests for its own changes; no conflicts.

## Branch and merge protocol

```bash
# Start a track session
git checkout main
git pull
git checkout -b phase-1.5/track-<X>/<task-or-day>

# ... work, commit small, push often
git push origin phase-1.5/track-X/...

# End-of-day merge (one merge session does ALL track merges)
git checkout main
git pull
for branch in phase-1.5/track-*/d<N>-*; do
  git merge --no-ff $branch
done
# resolve conflicts (PROGRESS-1.5.md union, code conflicts case-by-case)
pytest -q
pnpm -C web test && pnpm -C web typecheck
git push origin main
git tag phase-1.5-d<N>-end
git push --tags
```

## Conflict resolution

- **PROGRESS-1.5.md conflicts**: take union. Both tracks' completed items survive.
- **KNOWLEDGE-1.5.md conflicts**: take union; under each section, both contributions survive.
- **Code conflicts in `orchestrator.py`**: Track A wins; other tracks' intent must be re-applied as a follow-up commit.
- **Migration conflicts** (same table touched by two tracks): rare; if it happens, Track A's migration runs first, the second track rebases.

## How to brief each track session

For each new Claude Code session in a track, paste this as the first message (substitute Track letter):

```
You are operating on Phase 1.5, Track X. Read in order:
1. /plan/phase-1.5/00-RULES-1.5.md
2. /plan/phase-1.5/PROGRESS-1.5.md (find your current track tasks)
3. /plan/phase-1.5/KNOWLEDGE-1.5.md
4. /plan/05-CODING-STANDARDS.md
5. /plan/phase-1.5/08-PARALLEL-TRACKS-1.5.md ("Track X" section + ownership rules)
6. The plan files relevant to your tasks (e.g., 04-SELF-HEALING-HARNESS.md for Track A on Day 2, 05-HYBRID-CHAT.md for Track B on Day 4)

You own only the folders listed in Track X's ownership row. Do not edit other tracks' folders. If you need a change from another track's territory, write it to PROGRESS-1.5.md under "Cross-track requests" and skip to a non-blocked task.

Check out branch phase-1.5/track-X/<task-or-day-id> from main. Make small commits with Conventional Commits format including 'phase-1.5' scope. Update PROGRESS-1.5.md as you close tasks.

Start with your first uncompleted task.
```

## When parallelism breaks down

If two tracks both end up needing a change to the same file/area:
1. **Pause one track**. The track whose work is more dependent on the other waits.
2. The unblocking track finishes its piece and merges to main.
3. The waiting track rebases off main and continues.

This is rare in Phase 1.5 thanks to clean ownership boundaries. If it happens twice in a day, fall back to sequential for that day.

## Single-session fallback

If you cannot run multiple sessions in parallel (only have one Claude Code instance available), follow `07-EXECUTION-PLAN-1.5.md` strictly in order. The day-by-day breakdown is designed to be doable in a single session per day.
