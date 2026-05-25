# 07 — Execution Plan (Phase 1.5)

Five days, 4–5 hours per day, ~25 hours total. Sequential plan below. Parallel orchestration in `08-PARALLEL-TRACKS-1.5.md`.

Task IDs use the format `P1.5-<DAY>-<AREA>-<NN>` where AREA is one of: `SETUP`, `HARNESS`, `CHAT`, `SEARCH`, `INTEG`, `BENCH`.

---

## Day 1 — Foundations, defects, baseline

**Goal:** infrastructure for measurement, fix the unsafe singletons, fix the retry counting bug. End-of-day: pipeline is correct (if not yet faster) and measurable.

### `P1.5-D1-SETUP-01` Create plan-1.5 branch + initial structure (15 min)
- Branch from `main`: `git checkout -b phase-1.5/setup/init`
- Confirm all `/plan/phase-1.5/` docs are present (this folder)
- Create `tests/fixtures/demo_corpus/` directory; gather 10 demo docs (anonymize as needed)
- Create empty `scripts/bench_phase_1_5.py`
- Commit: `chore(phase-1.5): bootstrap phase 1.5 plan and fixture directory`

### `P1.5-D1-BENCH-01` Baseline benchmark (45 min)
- Implement minimal `scripts/bench_phase_1_5.py` (CLI that uploads 10 docs, queries durations from DB, prints table)
- Run against current `main` deployment
- Record results in `KNOWLEDGE-1.5.md` under "Performance log → Baseline"
- Commit: `chore(bench,phase-1.5): add baseline benchmark script and capture baseline numbers`

### `P1.5-D1-HARNESS-01` Fix agent singleton bug (`D-AGENT-01`) (60 min)
- Refactor `agents/base.py`, `agents/classifier.py`, `agents/extractor.py`
- Remove module-level `classifier_agent` and `extractor_agent`
- Pass `page_image` / `page_images` as `run()` arguments
- Update orchestrator to instantiate per pipeline run
- Add regression test `tests/unit/test_agents_concurrency.py`
- Commit: `refactor(agents,phase-1.5): instantiate agents per run, remove singleton state (D-AGENT-01)`

### `P1.5-D1-HARNESS-02` Fix retry_count bug (`D-RETRY-01`) (30 min)
- Remove the SQL increment in `extracted_fields_repo.update_verification`
- Add explicit increment in orchestrator's retry path
- Add regression test: fixture deliberately needs 2 retries; assert `retry_count == 2` at end
- Commit: `fix(harness,phase-1.5): increment retry_count only on actual retry (D-RETRY-01)`

### `P1.5-D1-HARNESS-03` LLM API retry with backoff (`D-LLM-RETRY-01`) (45 min)
- Add `utils/retry.py` with `with_retry` helper
- Wrap `anthropic_client.messages.create` and `openai_embeddings.get_embeddings`
- Add test: mock client raising 429 twice then succeeding
- Commit: `feat(integrations,phase-1.5): retry transient LLM errors with backoff (D-LLM-RETRY-01)`

### `P1.5-D1-SETUP-02` Test harness scaffolding (30 min)
- Add `tests/conftest.py` with shared fixtures: db session, mocked anthropic client, fixture document loader
- Add `tests/integration/test_pipeline_smoke.py` — runs one document through full pipeline against mocked LLMs
- Confirm `pytest -q` discovers and runs tests
- Commit: `test(infra,phase-1.5): add pytest scaffolding and shared fixtures`

### `P1.5-D1-SETUP-03` Update PROGRESS-1.5.md + KNOWLEDGE-1.5.md, merge (15 min)
- Mark all D1 tasks `[x]`
- Note baseline numbers in KNOWLEDGE-1.5.md
- Merge `phase-1.5/setup/init` → `main` via PR or fast-forward
- Tag commit `phase-1.5-d1-end`

---

## Day 2 — Self-healing harness core

**Goal:** groundedness check, adaptive retry budgets, schema additions. End-of-day: hallucinations get caught and the harness adapts retries intelligently.

### `P1.5-D2-HARNESS-04` Schema migration for new fields (15 min)
- Alembic migration: add `extracted_fields.is_grounded`, `groundedness_method`, `importance`, `retry_budget`, `retry_budget_remaining`
- Add `documents.processing_state` JSONB
- Apply migration locally; verify with `psql`
- Commit: `feat(db,phase-1.5): add groundedness and retry-budget columns`

### `P1.5-D2-HARNESS-05` Groundedness module (`D-GROUND-01`) (90 min)
- New file `services/pipeline/groundedness.py` per `04-SELF-HEALING-HARNESS.md`
- Implement `check_groundedness`, `normalize_text`, `identifier_variants`, `date_variants`, `number_variants`
- Unit tests for each variant matcher with positive and negative cases (15+ tests)
- Commit: `feat(harness,phase-1.5): add deterministic groundedness check (D-GROUND-01)`

### `P1.5-D2-HARNESS-06` Verifier schema updates (45 min)
- Add `retry_budget` and `importance` to `FieldVerification`
- Update verifier prompt to emit these fields
- Update schema architect prompt to set `importance` per field
- Update Pydantic models in `agents/verifier.py` and `agents/schema_architect.py`
- Commit: `feat(agents,phase-1.5): verifier emits retry_budget and importance per field`

### `P1.5-D2-HARNESS-07` Orchestrator adaptive retry loop (`D-RETRY-01` continuation + `D-VERIFIER-02`) (90 min)
- Replace current `_verify()` logic with the new `_ground_verify_retry()` loop per `04-SELF-HEALING-HARNESS.md`
- Wire `combine_signals` to compute final per-field confidence
- Max iterations cap (4)
- Per-field budget bookkeeping
- Integration test: fixture document with one deliberately-hallucinated value → loop detects → retries → resolves
- Commit: `feat(pipeline,phase-1.5): adaptive ground+verify+retry loop with per-field budgets`

### `P1.5-D2-HARNESS-08` Vectorization tracing (`D-VECTORIZER-TRACE-01`) (15 min)
- Wrap `vectorize_document` with langfuse span using passed `trace_id`
- Commit: `feat(pipeline,phase-1.5): add tracing span around vectorization`

### `P1.5-D2-HARNESS-09` Verifier text-sample expansion (`D-VERIFIER-01`) (30 min)
- Expand text_sample from 4000 → 16000 chars
- For very long documents, add per-field source_location slicing
- Test: multi-page fixture with required field on page 3
- Commit: `fix(verifier,phase-1.5): expand verifier text context to catch later-page fields`

### `P1.5-D2-BENCH-02` Mid-phase benchmark + merge (30 min)
- Run benchmark script
- Compare against baseline; record in KNOWLEDGE-1.5.md
- Pipeline may be slightly slower at this point (more rigor) — that's OK
- Merge `phase-1.5/harness/*` → main; tag `phase-1.5-d2-end`

---

## Day 3 — Parallelism + summarizer

**Goal:** within-document parallelism, real LLM summary, vocab cache. End-of-day: pipeline is meaningfully faster.

### `P1.5-D3-HARNESS-10` LLM summarizer agent (`D-SUMMARY-01`) (60 min)
- New `agents/summarizer.py` (Haiku, ~150 token output target)
- Prompt: short, factual summary; no fluff
- Integration into orchestrator (will be wired into parallel stage next)
- Unit test
- Commit: `feat(agents,phase-1.5): add LLM summarizer agent for document summaries`

### `P1.5-D3-HARNESS-11` Within-document parallelism (45 min)
- Refactor orchestrator: `summarize` ∥ `classify` (gather)
- Refactor: `integrate` ∥ `vectorize` (gather)
- Status mapping: emit pipeline_events for both even when concurrent
- `asyncio.gather(return_exceptions=True)` with explicit handling (summarize/vectorize fallbacks)
- Integration test: process a document, verify event timestamps show overlap
- Commit: `perf(pipeline,phase-1.5): parallelize summarize+classify and integrate+vectorize`

### `P1.5-D3-HARNESS-12` Pipeline resumability (`D-PIPELINE-01`) (75 min)
- Implement page-images-to-Storage during text extraction
- Implement `documents.processing_state` writes after each stage
- On orchestrator init, hydrate from `processing_state` if status != 'uploaded'
- Test: kill worker mid-document, restart, verify completion
- Commit: `feat(pipeline,phase-1.5): persist processing state for crash resumability (D-PIPELINE-01)`

### `P1.5-D3-SEARCH-01` VocabCache process-level with TTL (`D-VOCAB-CACHE-01`) (60 min)
- Refactor `vocab_cache.py` to a process-shared `VocabCacheStore` with per-user TTL
- Per-key lock pattern for safe concurrent loads
- TTL = 60s; no invalidation hook in Phase 1.5 (acceptable trade-off)
- Tests: assert single DB load under hot loop; assert reload after TTL
- Commit: `perf(search,phase-1.5): cache vocab per user with 60s TTL (D-VOCAB-CACHE-01)`

### `P1.5-D3-SEARCH-02` Fuzzy match broader coverage (`D-FUZZY-MATCH-01`) (30 min)
- Extend `_fuzzy_match` to folders, tags, domains
- Tests for each
- Commit: `feat(search,phase-1.5): fuzzy-match folders/tags/domains in resolver`

### `P1.5-D3-HARNESS-13` Anthropic + OpenAI semaphore caps (15 min)
- Process-level semaphores: Anthropic = 10, OpenAI = 5
- Applied in client wrappers
- Commit: `feat(integrations,phase-1.5): concurrency-cap LLM clients to protect rate limits`

### `P1.5-D3-BENCH-03` Mid-phase benchmark + merge (30 min)
- Run benchmark
- Expect: pipeline end-to-end p50 down by ~30% from D2
- Record numbers; merge to main; tag `phase-1.5-d3-end`

---

## Day 4 — Hybrid chat + JWT auth

**Goal:** KG-grounded chat with vector fusion, multi-turn history, JWT auth. End-of-day: chat is the demo-worthy moment.

### `P1.5-D4-CHAT-01` Schema for chat threads + messages (15 min)
- Alembic migration: `chat_threads`, `chat_messages`, RLS policies
- Commit: `feat(db,phase-1.5): add chat_threads and chat_messages tables`

### `P1.5-D4-CHAT-02` Question router (`05-HYBRID-CHAT.md`) (60 min)
- New `services/chat/router.py` with `RoutingHint` model
- Haiku-based classification with prompt
- Tests: 12 representative questions cover the intent table
- Commit: `feat(chat,phase-1.5): add question router for hybrid retrieval routing`

### `P1.5-D4-CHAT-03` KG retriever (`D-KG-CHAT-01`) (90 min)
- New `services/chat/kg_retriever.py`
- Implements: entity resolution (alias + relation_term + fuzzy + history-aware), relationship traversal, field-name search, time filter, dedupe
- Tests with seeded entity graph
- Commit: `feat(chat,phase-1.5): replace _kg_lookup with KGRetriever supporting relationships (D-KG-CHAT-01)`

### `P1.5-D4-CHAT-04` Vector retriever upgrade (60 min)
- Add BM25 alongside vector cosine in cross-doc retriever
- Entity-boost via document_entities
- Single-doc retriever: add BM25
- Tests
- Commit: `feat(chat,phase-1.5): hybrid vector+BM25 retrieval with entity boost`

### `P1.5-D4-CHAT-05` Fusion + responder (75 min)
- New `services/chat/fusion.py`
- Responder accepts `context_items` (typed) instead of raw chunks
- Updated system prompt with KG/chunk dual-citation contract
- Conversation history loaded from `chat_messages` (last ~12 messages)
- Update `routes/chat.py` to use thread_id; auto-create thread if missing
- Persist user/assistant messages with citations
- Commit: `feat(chat,phase-1.5): fusion layer + thread history; structured citations for KG and chunks`

### `P1.5-D4-CHAT-06` Chat threads BFF + frontend (60 min)
- New `web/app/api/threads/route.ts` (list + create), `web/app/api/threads/[id]/route.ts` (load history, delete)
- Frontend: thread list sidebar on `/chat` page; per-doc auto-thread on document detail
- Citation badges differentiate KG fact vs chunk
- Commit: `feat(web,phase-1.5): chat thread UI with history and dual citations`

### `P1.5-D4-AUTH-01` JWT verification on `/search` and `/chat` (`D-AUTH-01`) (45 min)
- New `deps.py` dependency `VerifiedUser` that verifies Supabase JWT via JWKS
- Apply to `/search`, `/chat`, new `/threads` routes
- Remove `user_id` from request bodies; derive from JWT subject
- Update Next.js BFF to forward `Authorization: Bearer <jwt>`
- Tests: missing JWT → 401; wrong JWT → 401; user A token cannot read user B → handled by RLS (already enforced)
- Commit: `fix(auth,phase-1.5): verify Supabase JWT on /search /chat /threads (D-AUTH-01)`

### `P1.5-D4-BENCH-04` Chat quality eval + merge (45 min)
- Implement `tests/integration/test_chat_quality.py` (10 Q&A pairs against seeded user)
- Run, capture cost
- Merge `phase-1.5/chat/*` → main; tag `phase-1.5-d4-end`

---

## Day 5 — Polish, eval, final benchmark, tag

**Goal:** close MED-class defects, run full benchmark, demo prep.

### `P1.5-D5-HARNESS-14` Bulk insert in extracted_fields_repo (`D-AGENT-INSERT-01`) (30 min)
- Convert loop to single INSERT VALUES
- Test
- Commit: `perf(repo,phase-1.5): bulk insert extracted fields in one statement`

### `P1.5-D5-CHAT-07` Citation unification confirmed (`D-CITATIONS-01`) (15 min)
- Verify chat responses emit both types
- Tests
- Commit if anything missed: `feat(chat,phase-1.5): finalize unified citation rendering`

### `P1.5-D5-INTEG-01` LOW-class cleanup (45 min)
- Remove `api/image-proecssing-error.txt`; add to `.gitignore`
- Decide on `/enqueue` body vs query (recommend body for plan-consistency; minor BFF tweak)
- Add `/api/folders`, `/api/tags`, `/api/graph` BFF routes only if time permits
- Commit per change

### `P1.5-D5-BENCH-05` Final benchmark (60 min)
- Run full benchmark
- Record final numbers in KNOWLEDGE-1.5.md
- Compare each SLO against target; document any misses with rationale
- Commit: `docs(perf,phase-1.5): capture final benchmark numbers`

### `P1.5-D5-INTEG-02` End-to-end smoke test (60 min)
- Reset demo user
- Upload 10 documents
- Wait for all to reach `ready`
- Run scripted search queries (chip composition)
- Run scripted chat questions (single doc + cross doc + follow-up)
- Verify Langfuse trace shows new spans (groundedness, retry loop, KG retrieval)
- File any defects as P1.6 backlog

### `P1.5-D5-INTEG-03` Demo recording (45 min)
- 90-second Loom against the smoke-test setup
- Hit the demo moments from `01-OBJECTIVES.md`

### `P1.5-D5-INTEG-04` Final sweep + tag (30 min)
- Verify `pytest -q` passes
- Verify `pnpm test && pnpm typecheck && pnpm lint` pass
- Verify PROGRESS-1.5.md fully checked
- Update KNOWLEDGE-1.5.md "Phase 1.5 completion" section
- Tag: `git tag -a v1.1-phase-1.5 -m "Phase 1.5 — Optimization, self-healing, hybrid chat"`
- Push tag

---

## Buffer policy

If you fall behind by end of Day 3:
- **Cut**: `D-FUZZY-MATCH-01` (Tier 2 fuzzy expansion) — low impact
- **Cut**: `D-AGENT-INSERT-01` bulk insert — minor perf win
- **Cut**: Day 5 LOW-class cleanup items
- **Do not cut**: groundedness check, adaptive retry loop, KG retriever, JWT auth, chat history, benchmarks

If you fall behind by end of Day 4:
- **Cut**: chat thread UI polish (functional bare-bones is OK)
- **Do not cut**: end-to-end smoke test, final benchmark, tag

If chat work blows up Day 4:
- **Move** to Day 5: single-doc BM25, chat thread BFF routes
- **Keep** on Day 4: KG retriever, fusion, basic thread persistence, JWT auth
