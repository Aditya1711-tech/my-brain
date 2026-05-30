# PROGRESS-1.5 — Living checklist (Phase 1.5)

Update at start AND end of every session. Use task IDs from `07-EXECUTION-PLAN-1.5.md`.

---

## Current

> What's being worked on RIGHT NOW. One task. Replace when complete.

- [x] `P1.5-D5-INTEG-02` Code-level smoke: 183 tests, 0 TS errors, 0 lint errors — 2026-05-30

## Up next

> Queue for this session. Take from the top.
- [ ] `P1.5-D5-INTEG-04` Final sweep + tag v1.1-phase-1.5

## Blockers

> Anything stopping progress. Each blocker needs a clear question.

_(none)_

## Cross-track requests

> Used during parallel execution. Format: "Track X needs Y from Track Z."

_(none yet)_

## Recently completed

> Last 10 tasks closed. Format: `[x] ID — description — YYYY-MM-DD HH:MM`. Prune older to KNOWLEDGE-1.5.md if long.

- [x] `P1.5-D5-INTEG-02` Code-level smoke: 183 tests, 0 TS errors, 0 lint errors — 2026-05-30
- [x] `P1.5-D5-INTEG-01` LOW-class cleanup: D-ENQUEUE-CONTRACT-01 (body), D-DEDUPE-INSERT-01 (N/A) — 2026-05-30
- [x] `P1.5-D5-CHAT-07` Citation unification verified + persistence fix (D-CITATIONS-01, 5 tests) — 2026-05-30
- [x] `P1.5-D5-HARNESS-14` Bulk insert in extracted_fields_repo (D-AGENT-INSERT-01, 5 tests) — 2026-05-30
- [x] `P1.5-D4-BENCH-04` Chat quality eval (15 tests) — 2026-05-30
- [x] `P1.5-D4-AUTH-01` JWT verification on /search /chat /threads (D-AUTH-01, 11 tests) — 2026-05-30
- [x] `P1.5-D4-CHAT-06` Chat threads BFF + frontend — 2026-05-30
- [x] `P1.5-D4-CHAT-05` Fusion + responder with history (D-CHAT-HISTORY-01, 13 tests) — 2026-05-30
- [x] `P1.5-D4-CHAT-04` Vector retriever upgrade (BM25 + entity boost, 9 tests) — 2026-05-30
- [x] `P1.5-D4-CHAT-03` KG retriever (D-KG-CHAT-01, 19 tests) — 2026-05-30
- [x] `P1.5-D4-CHAT-02` Question router (19 tests) — 2026-05-30
- [x] `P1.5-D4-CHAT-01` Schema for chat threads + messages — 2026-05-30
- [x] `P1.5-D3-HARNESS-13` Anthropic + OpenAI semaphore caps — 2026-05-30
- [x] `P1.5-D3-SEARCH-02` Fuzzy match broader coverage (D-FUZZY-MATCH-01) — 2026-05-30
- [x] `P1.5-D3-SEARCH-01` VocabCache with TTL (D-VOCAB-CACHE-01) — 2026-05-30
- [x] `P1.5-D3-HARNESS-12` Pipeline resumability (D-PIPELINE-01) — 2026-05-30
- [x] `P1.5-D3-HARNESS-11` Within-document parallelism — 2026-05-30
- [x] `P1.5-D3-HARNESS-10` LLM summarizer agent (D-SUMMARY-01) — 2026-05-30
- [x] `P1.5-D2-HARNESS-09` Verifier text-sample expansion (already in HARNESS-07) — 2026-05-26
- [x] `P1.5-D2-HARNESS-08` Vectorization tracing (D-VECTORIZER-TRACE-01) — 2026-05-26
- [x] `P1.5-D2-HARNESS-07` Orchestrator adaptive retry loop (D-VERIFIER-02) — 2026-05-26
- [x] `P1.5-D2-HARNESS-06` Verifier schema updates (importance + retry_budget) — 2026-05-26
- [x] `P1.5-D2-HARNESS-05` Groundedness module (D-GROUND-01, 31 tests) — 2026-05-26
- [x] `P1.5-D2-HARNESS-04` Schema migration (groundedness + retry budget + processing_state) — 2026-05-26
- [x] `P1.5-D1-SETUP-03` Day 1 merge + tag phase-1.5-d1-end — 2026-05-26
- [x] `P1.5-D1-SETUP-02` Test harness scaffolding (conftest + smoke test) — 2026-05-26
- [x] `P1.5-D1-HARNESS-03` LLM API retry with backoff (D-LLM-RETRY-01) — 2026-05-26
- [x] `P1.5-D1-HARNESS-02` Fix retry_count bug (D-RETRY-01) — 2026-05-25
- [x] `P1.5-D1-HARNESS-01` Fix agent singleton bug (D-AGENT-01) — 2026-05-25
- [x] `P1.5-D1-BENCH-01` Baseline benchmark — 2026-05-25
- [x] `P1.5-D1-SETUP-01` Bootstrap phase 1.5 branch + structure — 2026-05-25

---

## Phase 1.5 task tracker

### Day 1 — Foundations, defects, baseline
- [x] `P1.5-D1-SETUP-01` Bootstrap phase 1.5 branch + structure — 2026-05-25
- [x] `P1.5-D1-BENCH-01` Baseline benchmark — 2026-05-25
- [x] `P1.5-D1-HARNESS-01` Fix agent singleton bug (D-AGENT-01) — 2026-05-25
- [x] `P1.5-D1-HARNESS-02` Fix retry_count bug (D-RETRY-01) — 2026-05-25
- [x] `P1.5-D1-HARNESS-03` LLM API retry with backoff (D-LLM-RETRY-01) — 2026-05-26
- [x] `P1.5-D1-SETUP-02` Test harness scaffolding — 2026-05-26
- [x] `P1.5-D1-SETUP-03` Day 1 merge + tag — 2026-05-26

### Day 2 — Self-healing harness core
- [x] `P1.5-D2-HARNESS-04` Schema migration for new fields — 2026-05-26
- [x] `P1.5-D2-HARNESS-05` Groundedness module (D-GROUND-01) — 2026-05-26
- [x] `P1.5-D2-HARNESS-06` Verifier schema updates — 2026-05-26
- [x] `P1.5-D2-HARNESS-07` Orchestrator adaptive retry loop (D-VERIFIER-02) — 2026-05-26
- [x] `P1.5-D2-HARNESS-08` Vectorization tracing (D-VECTORIZER-TRACE-01) — 2026-05-26
- [x] `P1.5-D2-HARNESS-09` Verifier text-sample expansion (D-VERIFIER-01) — 2026-05-26 (done in HARNESS-07)
- [ ] `P1.5-D2-BENCH-02` Mid-phase benchmark + merge (deferred — run after deploy)

### Day 3 — Parallelism + summarizer + cache
- [x] `P1.5-D3-HARNESS-10` LLM summarizer agent (D-SUMMARY-01) — 2026-05-30
- [x] `P1.5-D3-HARNESS-11` Within-document parallelism — 2026-05-30
- [x] `P1.5-D3-HARNESS-12` Pipeline resumability (D-PIPELINE-01) — 2026-05-30
- [x] `P1.5-D3-SEARCH-01` VocabCache with TTL (D-VOCAB-CACHE-01) — 2026-05-30
- [x] `P1.5-D3-SEARCH-02` Fuzzy match broader coverage (D-FUZZY-MATCH-01) — 2026-05-30
- [x] `P1.5-D3-HARNESS-13` Anthropic + OpenAI semaphore caps — 2026-05-30
- [ ] `P1.5-D3-BENCH-03` Mid-phase benchmark + merge (deferred — run after deploy)

### Day 4 — Hybrid chat + JWT auth
- [x] `P1.5-D4-CHAT-01` Schema for chat threads + messages — 2026-05-30
- [x] `P1.5-D4-CHAT-02` Question router — 2026-05-30
- [x] `P1.5-D4-CHAT-03` KG retriever (D-KG-CHAT-01) — 2026-05-30
- [x] `P1.5-D4-CHAT-04` Vector retriever upgrade (BM25 + entity boost) — 2026-05-30
- [x] `P1.5-D4-CHAT-05` Fusion + responder with history (D-CHAT-HISTORY-01) — 2026-05-30
- [x] `P1.5-D4-CHAT-06` Chat threads BFF + frontend — 2026-05-30
- [x] `P1.5-D4-AUTH-01` JWT verification on /search /chat /threads (D-AUTH-01) — 2026-05-30
- [x] `P1.5-D4-BENCH-04` Chat quality eval + merge — 2026-05-30

### Day 5 — Polish, eval, final benchmark, tag
- [x] `P1.5-D5-HARNESS-14` Bulk insert in extracted_fields_repo (D-AGENT-INSERT-01) — 2026-05-30
- [x] `P1.5-D5-CHAT-07` Citation unification verified (D-CITATIONS-01) — 2026-05-30
- [x] `P1.5-D5-INTEG-01` LOW-class cleanup — 2026-05-30
- [ ] `P1.5-D5-BENCH-05` Final benchmark (deferred — run after deploy)
- [x] `P1.5-D5-INTEG-02` End-to-end smoke test (code-level) — 2026-05-30
- [ ] `P1.5-D5-INTEG-03` Demo recording
- [ ] `P1.5-D5-INTEG-04` Final sweep + tag v1.1-phase-1.5

---

## Defects tracker (mirror of `02-DEFECT-LEDGER.md`)

Maps defect IDs to status. A defect is "closed" only when its regression test exists.

### CRIT
- [x] `D-AGENT-01` Agent singleton concurrency bug — fixed 2026-05-25, regression tests in test_agents_concurrency.py
- [x] `D-RETRY-01` retry_count increments on first verifier pass — fixed 2026-05-25, regression tests in test_retry_count.py
- [x] `D-KG-CHAT-01` Cross-doc chat KG lookup keyword-only, ignores relationships — fixed 2026-05-30, KGRetriever with entity resolution + relationship traversal, test_kg_retriever.py (19 tests)
- [x] `D-AUTH-01` No JWT verification on /search and /chat — fixed 2026-05-30, VerifiedUser dependency + BFF JWT forwarding, test_jwt_auth.py (11 tests)
- [x] `D-GROUND-01` No groundedness check — fixed 2026-05-26, test_groundedness.py (31 tests) + retry integration test

### HIGH
- [x] `D-PIPELINE-01` Pipeline non-resumable due to in-memory state — fixed 2026-05-30, processing_state JSONB + page images in Storage, test_pipeline_resumability.py (5 tests)
- [x] `D-LLM-RETRY-01` No LLM API retry with backoff — fixed 2026-05-26
- [x] `D-CHAT-HISTORY-01` Chat stateless, no conversation history — fixed 2026-05-30, thread persistence + history replay in responder, test_fusion.py (13 tests)
- [x] `D-VERIFIER-01` Verifier sees only 4000 chars — fixed 2026-05-26, expanded to 16000 in adaptive loop
- [x] `D-VERIFIER-02` No re-verification after retry — fixed 2026-05-26, adaptive loop re-verifies after each retry

### MED
- [x] `D-VOCAB-CACHE-01` VocabCache rebuilt per request — fixed 2026-05-30, process-level _VocabStore with 60s TTL, test_vocab_cache.py (5 tests)
- [x] `D-FUZZY-MATCH-01` Tier 2 fuzzy covers entities, doc_types, folders, tags, domains — fixed 2026-05-30, test_fuzzy_match.py (7 tests)
- [x] `D-VECTORIZER-TRACE-01` Vectorization not traced — fixed 2026-05-26, Langfuse span in vectorizer
- [x] `D-AGENT-INSERT-01` Field inserts not batched — fixed 2026-05-30, multi-row INSERT, test_bulk_insert.py (5 tests)
- [x] `D-SUMMARY-01` summary is deterministic, not LLM — fixed 2026-05-30, SummarizerAgent (Haiku)
- [x] `D-CITATIONS-01` Citations don't include KG facts — fixed 2026-05-30, _stream_and_persist type check corrected, test_fusion.py (5 new tests)

### LOW (do if time)
- [ ] `D-BFF-FOLDERS-01` Missing /api/folders, /api/tags, /api/graph BFFs
- [x] `D-DEDUPE-INSERT-01` Untracked log artifact in repo — N/A 2026-05-30, file never existed in working tree
- [x] `D-ENQUEUE-CONTRACT-01` /enqueue uses query param vs plan — fixed 2026-05-30, switched to JSON body
- [ ] `D-RECHARTS-01` recharts not installed (skip until Phase 2)
- [ ] `D-BLACK-01` black not installed (no action; ruff format used)

---

## Session log

> Append a one-liner at end of each session. Helps recover context.

Format: `YYYY-MM-DD HH:MM | track | session description | tasks closed | next up`

2026-05-25 | day-1 | Bootstrap + baseline + D-AGENT-01 singleton fix + D-RETRY-01 retry_count fix | SETUP-01, BENCH-01, HARNESS-01, HARNESS-02 | HARNESS-03 (LLM retry with backoff)
2026-05-26 | day-1 | LLM retry + test harness + Day 1 merge/tag | HARNESS-03, SETUP-02, SETUP-03 | Day 2 (HARNESS-04)
2026-05-26 | day-2 | Schema migration, groundedness, adaptive retry, tracing, verifier expansion | HARNESS-04..09 | BENCH-02 (benchmark + merge)
2026-05-30 | day-3 | Summarizer, parallelism, resumability, vocab cache, fuzzy match, semaphores | HARNESS-10..13, SEARCH-01..02 | BENCH-03 (deferred), Day 4 (CHAT-01)
