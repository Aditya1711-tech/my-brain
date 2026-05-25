# 02 — Defect Ledger

Every defect from the state report, with: severity, where it lives, what's wrong, how to fix it, what test proves it fixed. Task IDs (e.g., `D-AGENT-01`) are referenced in `PROGRESS-1.5.md` and `07-EXECUTION-PLAN-1.5.md`.

Severity: **CRIT** (blocks Phase 2 or causes wrong answers), **HIGH** (security or data integrity), **MED** (perf/UX), **LOW** (polish).

---

## CRIT-class defects

### `D-AGENT-01` — Agent singleton concurrency bug

**Severity:** CRIT
**Location:** `api/app/agents/classifier.py`, `api/app/agents/extractor.py` (module-level `classifier_agent = ClassifierAgent()` and `extractor_agent = ExtractorAgent()`)
**Issue:** Both agents store `_page_image` / `_page_images` on `self`. With `max_jobs=5` in `worker/worker.py`, multiple concurrent pipeline runs share the same singleton and overwrite each other's images.
**Fix:**
- Remove module-level singletons
- Instantiate agents per pipeline run inside `PipelineOrchestrator`
- Pass page images as **method arguments** to `run()`, not as instance attributes
- Update `Agent.run()` signature to optionally accept multimodal inputs
**Regression test:** `tests/unit/test_agents_concurrency.py` — spin two `asyncio.gather` calls into the classifier with different images; assert each returns the correct classification for its own image.
**Touches:** `agents/base.py`, `agents/classifier.py`, `agents/extractor.py`, `services/pipeline/orchestrator.py`

---

### `D-RETRY-01` — `retry_count` increments on first verifier pass

**Severity:** CRIT
**Location:** `api/app/repositories/extracted_fields_repo.py` — `update_verification()` SQL: `retry_count = retry_count + CASE WHEN :needs_retry THEN 1 ELSE 0 END`
**Issue:** The verifier's first pass is not a retry, but the SQL increments `retry_count` based on `needs_retry`. After the first verification, flagged fields already have `retry_count=1`. The orchestrator checks `retry_count < MAX_RETRY_COUNT (2)`, so only one actual re-extraction happens, not two as planned.
**Fix:**
- Remove the increment from `update_verification()`
- Increment `retry_count` **only** in the orchestrator at the moment a retry is actually triggered (after `_verify()` decides to retry, before calling `extractor_agent.run()` again)
**Regression test:** Run pipeline with a fixture that needs 2 retries; assert `extracted_fields.retry_count` equals 2 (not 1 or 3); assert two retry events appear in `document_pipeline_events`.
**Touches:** `repositories/extracted_fields_repo.py`, `services/pipeline/orchestrator.py`

---

### `D-KG-CHAT-01` — Cross-doc chat KG lookup is keyword-only and ignores relationships

**Severity:** CRIT
**Location:** `api/app/routes/chat.py` — `_kg_lookup()`
**Issue:**
- Fetches 50 most recent current facts, filters by raw substring match against question text
- No semantic matching — "spouse" in question won't match "wife" in entity, "passport expiry" won't match "expiry_date"
- Never queries `entity_relationships` at all (relationship graph is unused)
- Never queries `document_entities` (cannot answer "what does Priya's passport say?")
**Fix:** Replace `_kg_lookup()` with a `KGRetriever` service (`services/chat/kg_retriever.py`) that:
- Uses relation term map + entity alias expansion to resolve "wife" → spouse entity
- Traverses relationships (one or two hops) when relevant relations are mentioned
- Returns structured `KGFact` objects with provenance (source_document_id, entity_id)
- Runs in parallel with vector retrieval (see `05-HYBRID-CHAT.md`)
**Regression test:** A fixture user has Priya (entity), passport (doc), `spouse_of` relation. Query "what is my wife's passport number" must return Priya's passport number from KG.
**Touches:** `routes/chat.py`, new `services/chat/kg_retriever.py`, `services/chat/retriever.py`, `services/chat/responder.py`

---

### `D-AUTH-01` — No JWT verification on `/search` and `/chat`

**Severity:** CRIT (security)
**Location:** `api/app/routes/search.py`, `api/app/routes/chat.py` — both accept `user_id` in body
**Issue:** Any caller who knows the FastAPI URL can query as any user. Safe behind the Next.js BFF (which only forwards `auth.uid()`), but the API itself is open.
**Fix:**
- Implement a `VerifiedUser` FastAPI dependency that verifies a Supabase JWT (passed in `Authorization: Bearer <jwt>`) using Supabase's JWKs
- Apply to `/search` and `/chat`
- Remove `user_id` from request bodies; derive from JWT
- Update Next.js BFF to forward the user's JWT instead of injecting user_id
- `/enqueue` keeps the `X-API-Key` shared-secret pattern (server-to-server)
**Regression test:** Hit `/search` and `/chat` without a JWT → 401. Hit with a JWT for user A and try to access user B's data → 403.
**Touches:** `api/app/deps.py` (new dependency), `routes/search.py`, `routes/chat.py`, `web/app/api/search/route.ts`, `web/app/api/chat/route.ts`

---

### `D-GROUND-01` — No groundedness check; verifier never literal-string-matches

**Severity:** CRIT (correctness)
**Location:** `api/app/agents/verifier.py` (LLM-only verification), no string-match logic anywhere
**Issue:** Verifier is an LLM reasoning about plausibility. A confident hallucination (e.g., a plausible-looking passport number not actually in the document) can receive `confidence=1.0`.
**Fix:** Add a deterministic **groundedness check** in `services/pipeline/groundedness.py`:
- For each extracted field, normalize (lowercase, strip whitespace, collapse separators) and check if `value` appears as a substring of normalized `raw_text`
- For dates, also try common format variants (ISO 8601, DD/MM/YYYY, MM/DD/YYYY, DD-Mon-YYYY)
- For identifiers, also try with/without spaces and hyphens
- For numbers/currency, normalize away formatting (commas, currency symbols)
- Add column `extracted_fields.is_grounded BOOLEAN` (additive migration)
- Run check after each extraction; if not grounded → cap confidence at 0.3 and set `needs_retry=true`
- On retry, extractor receives "the value X you returned for field Y was not found in the source — re-examine"
**Regression test:** Inject a fake field value not in raw_text → check returns `is_grounded=false`, confidence capped, retry triggered.
**Touches:** new `services/pipeline/groundedness.py`, `services/pipeline/orchestrator.py`, `migrations/`, `repositories/extracted_fields_repo.py`

---

### `D-PIPELINE-01` — Pipeline non-resumable due to in-memory state

**Severity:** HIGH
**Location:** `api/app/services/pipeline/orchestrator.py` — `self._last_extraction` and `self._last_extraction_output`
**Issue:** If a worker crashes mid-document, the next run picks up from the last committed status but the in-memory `_last_extraction` (RawExtraction with page_images) is gone. Subsequent stages can't access page images for image-heavy PDFs.
**Fix:**
- Persist `RawExtraction` minimal essentials to `documents` table (or a new `document_processing_state` table) including a reference to where page images live (Supabase Storage path, since they were already rendered)
- On resume, hydrate from DB instead of relying on `self._last_extraction`
- Store page images in Storage under `<user_id>/<doc_id>/page_images/<n>.png` when they're rendered, so they're available to any worker
**Regression test:** Kill worker after `extracting_text` commit, restart, confirm pipeline completes successfully with page images available.
**Touches:** new migration, `services/pipeline/orchestrator.py`, `parsing/pdf.py`, possibly `integrations/supabase_client.py`

---

## HIGH-class defects

### `D-LLM-RETRY-01` — No LLM API retry with backoff

**Severity:** HIGH
**Location:** `api/app/integrations/anthropic_client.py`, `api/app/integrations/openai_embeddings.py`
**Issue:** Transient errors (429, 5xx, network) fail the document. Plan called for "Retry with backoff (max 3)" but it's not implemented anywhere.
**Fix:**
- Add retry decorator with exponential backoff (base 1s, cap 8s, max 3 attempts) to both client wrappers
- Retry only on transient errors: `httpx.ConnectError`, `httpx.ReadTimeout`, 429, 500, 502, 503, 504
- Permanent errors (400, schema validation) bypass retry
- Log each retry attempt; emit a Langfuse span if a retry happens
**Regression test:** Mock anthropic_client to fail twice then succeed; assert agent returns successful result on third attempt; assert one log line per failure.
**Touches:** `integrations/anthropic_client.py`, `integrations/openai_embeddings.py`, possibly a small `utils/retry.py`

---

### `D-CHAT-HISTORY-01` — Chat is stateless, no conversation history

**Severity:** HIGH (UX)
**Location:** `api/app/routes/chat.py`, `web/app/api/chat/route.ts`
**Issue:** `ChatRequest` takes a single `question: str`. Every turn is a cold start.
**Fix:**
- New tables (additive migration): `chat_threads(id, user_id, scope, document_id_nullable, title, created_at)` and `chat_messages(id, thread_id, user_id, role, content, citations_jsonb, created_at)`
- Modify `ChatRequest` to accept `thread_id` (optional — auto-create if missing) + `message: str`
- Responder loads the last N messages (config: 20) from the thread and includes in Claude messages array
- Token-budget the history: if total context exceeds a cap, drop oldest messages
- Frontend: thread list view (Phase 1.5: simple list; one thread per scope is OK initially)
**Regression test:** Two-turn conversation: turn 1 asks about Priya's passport; turn 2 asks "and the expiry date?" — turn 2 must resolve "the" to Priya's passport from history.
**Touches:** new migration, `routes/chat.py`, `services/chat/responder.py`, `services/chat/thread_repo.py` (new), frontend chat components

---

### `D-VERIFIER-01` — Verifier sees only 4000 chars; misses fields on later pages

**Severity:** HIGH
**Location:** `api/app/agents/verifier.py` — `text_sample[:4000]`
**Issue:** Multi-page documents with fields on later pages can't be verified — verifier accepts whatever the extractor returned without ability to check.
**Fix:**
- Expand `text_sample` to up to 16k chars OR provide the verifier the original text region per field (each `ExtractedField.source_location` could carry a char-range hint and the verifier gets that slice)
- Simpler approach (recommended): pass full `raw_text` truncated to model's input budget; for very long docs, send per-field slices around `source_location`
**Regression test:** Multi-page fixture where the required field appears on page 3; verify groundedness check sees it.
**Touches:** `agents/verifier.py`, `services/pipeline/orchestrator.py`

---

### `D-VERIFIER-02` — No re-verification after retry

**Severity:** HIGH
**Location:** `api/app/services/pipeline/orchestrator.py` — `_verify()`
**Issue:** After extractor retry, the new value is stored but the verifier is not re-run on retry results. Final confidence reflects the original (probably bad) extraction.
**Fix:**
- After retry, re-run verifier on the affected fields
- Update confidence to reflect the post-retry verification
- The retry budget (see `04-SELF-HEALING-HARNESS.md`) decides when to stop the verify/retry loop
**Regression test:** Fixture with deliberately-bad first extraction → retry → verifier re-runs → final confidence reflects retry quality.
**Touches:** `services/pipeline/orchestrator.py`

---

## MED-class defects

### `D-VOCAB-CACHE-01` — VocabCache rebuilt per request

**Severity:** MED
**Location:** `api/app/services/search/vocab_cache.py`
**Issue:** 7 SQL queries on every `/search` call. For users with many entities, this could be a meaningful share of search latency.
**Fix:**
- Move VocabCache to a process-level `dict[user_id, CachedVocab]` with TTL (default 60s) and invalidation hook
- On entity/folder/tag/document insert in the worker, publish an invalidation message via Redis pub/sub or via a "vocab version" counter the FastAPI process checks lazily
- Simpler-but-acceptable: TTL only, no invalidation. Stale vocab for up to 60s is fine (search just won't pick up brand new entities for a minute)
**Regression test:** Issue 100 `/search` calls in a hot loop with same user_id → assert vocab DB queries are issued only once. Wait > TTL → assert it reloads.
**Touches:** `services/search/vocab_cache.py`, possibly `worker/tasks.py` for invalidation

---

### `D-FUZZY-MATCH-01` — Tier 2 only fuzzy-matches entities and doc_types

**Severity:** MED
**Location:** `api/app/services/search/resolver.py` — `_fuzzy_match()`
**Issue:** Trigram match only on `entities` and `documents.doc_type`. Folders, tags, file_types, domains only get exact match in Tier 1.
**Fix:** Extend `_fuzzy_match` to also try folders, tags, and domains (file_types are a fixed vocabulary — exact match is sufficient).
**Regression test:** Fuzzy-match common typos for folder names, tag names, domain names.
**Touches:** `services/search/resolver.py`

---

### `D-VECTORIZER-TRACE-01` — Vectorization not traced

**Severity:** MED
**Location:** `api/app/services/pipeline/vectorizer.py` — `trace_id` parameter accepted but unused
**Issue:** Langfuse trace for a document doesn't include the vectorization span. Demo says "look at the trace" — incomplete picture.
**Fix:** Add `with langfuse.trace(...).span("vectorization")` around the chunking + embeddings batch.
**Regression test:** Run pipeline → fetch Langfuse trace → assert `vectorization` span exists with chunk count and embedding count.
**Touches:** `services/pipeline/vectorizer.py`

---

### `D-AGENT-INSERT-01` — Field inserts loop one-INSERT-per-field

**Severity:** MED
**Location:** `api/app/repositories/extracted_fields_repo.py` — `bulk_insert()` not truly bulk
**Issue:** Loop of single INSERTs. For docs with 10-15 fields, the DB round-trips add up.
**Fix:** Use `executemany`-style batch insert or a single `INSERT ... VALUES (...), (...), ...` statement.
**Regression test:** Insert 20 fields → assert exactly 1 DB statement executed (count via logging).
**Touches:** `repositories/extracted_fields_repo.py`

---

### `D-SUMMARY-01` — `documents.summary` is deterministic field concatenation, not LLM summary

**Severity:** MED
**Location:** `api/app/services/pipeline/orchestrator.py` (or wherever summary is built)
**Issue:** Summary is `"; ".join([f"{name}: {value}" for f in fields[:10]])`. Not useful for chunk context or search ranking. Plan said "LLM summary set early so search works immediately."
**Fix:**
- Add a sixth lightweight step early in the pipeline (after `extracting_text`, before `classified`) that generates an LLM summary (50-100 words) from raw_text + classifier hint
- Use Haiku for cost; sub-second latency expected
- Summary feeds into search results, chunk context, and chat retriever
**Regression test:** A processed document's summary is a human-readable paragraph, not a concatenation.
**Touches:** new `agents/summarizer.py` or inline in orchestrator, `services/pipeline/orchestrator.py`

---

### `D-CITATIONS-01` — Citations include chunks but not KG facts

**Severity:** MED
**Location:** `api/app/services/chat/responder.py`
**Issue:** Citations are emitted only for chunks. KG-derived answers cite "facts" implicitly via prompt but the UI gets no structured citation.
**Fix:** Introduce a unified `Citation` type: `{type: "kg_fact"|"chunk", id, source_document_id, label}`. Emit citations for both. Frontend renders both with different icons.
**Regression test:** A chat response that draws from both KG and chunks emits at least one citation of each type.
**Touches:** `services/chat/responder.py`, frontend chat citation rendering

---

## LOW-class defects (do if time)

### `D-BFF-FOLDERS-01` — `/api/folders`, `/api/tags`, `/api/graph` BFF routes missing

**Severity:** LOW
**Location:** `web/app/api/` — these routes don't exist
**Issue:** Frontend hits Supabase directly. Works (RLS protects), but inconsistent with planned BFF pattern.
**Fix:** Add Next.js route handlers. Low priority — not blocking anything.
**Regression test:** GET each route returns expected shape.

---

### `D-DEDUPE-INSERT-01` — Image-processing-error.txt artifact committed

**Severity:** LOW
**Location:** `api/image-proecssing-error.txt`
**Fix:** Add to `.gitignore`, remove from working tree.

---

### `D-ENQUEUE-CONTRACT-01` — `/enqueue` uses query param instead of body

**Severity:** LOW
**Location:** `api/app/routes/documents.py`
**Fix:** Either accept body OR update plan docs. Not breaking — pick consistency.

---

### `D-RECHARTS-01` — `recharts` was planned but not installed

**Severity:** LOW (no impact)
**Fix:** Skip or install if Phase 1.5 introduces any charts. Defer to Phase 2 (financial dashboards need it).

---

### `D-BLACK-01` — `black` listed in plan, not installed

**Severity:** LOW (ruff format covers it)
**Fix:** Update plan, no code change needed. Already documented as deviation.

---

## Closing a defect

A defect is closed only when:
1. The fix is committed on `main`
2. A regression test exists that fails on the pre-fix code and passes after the fix
3. `PROGRESS-1.5.md` marks the task `[x]`
4. If the defect changes data shape (new column, new table), the migration is applied and `KNOWLEDGE-1.5.md` updated under "Schema state"

A defect is **not closed** by "I fixed it and it seems to work." Test or it's not done.
