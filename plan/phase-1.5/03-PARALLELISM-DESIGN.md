# 03 — Parallelism Design

How Phase 1.5 makes the pipeline fast and concurrent **without** creating race conditions or compromising correctness.

## Three layers of parallelism

### Layer 1: Across documents (already exists, currently broken)
`arq` runs up to `max_jobs=5` document jobs concurrently. **This is already in place** but the agent singletons (`classifier_agent`, `extractor_agent`) make it unsafe (see `D-AGENT-01`). Phase 1.5 fixes the singletons → cross-document parallelism becomes safe.

### Layer 2: Within a document (new in Phase 1.5)
Stages that don't depend on each other run concurrently for the same document.

### Layer 3: Within a single agent call (new in Phase 1.5)
The retry loop currently does N sequential extractor calls if N fields need retry. We batch them into a single call.

---

## Layer 1: Cross-document concurrency

### The fix
Remove module-level agent singletons. Pattern change:

```python
# BEFORE — unsafe
classifier_agent = ClassifierAgent()

class ClassifierAgent(Agent):
    def set_page_image(self, image_bytes): self._page_image = image_bytes
    async def run(self, input_data): ...  # reads self._page_image

# AFTER — safe
class ClassifierAgent(Agent):
    async def run(self, input_data: ClassifierInput, *, page_image: bytes | None = None) -> ClassifierOutput:
        # page_image passed as arg; no instance state
        ...

# Orchestrator now creates per-document:
class PipelineOrchestrator:
    def __init__(self, db):
        self.classifier = ClassifierAgent()  # new instance per pipeline run
        self.extractor = ExtractorAgent()
        ...
```

Per-document instances are cheap (no model client per instance — those stay singletons; only the agent wrapper changes). Concurrent pipelines now have isolated agent objects.

### Why this also helps observability
Each agent instance carries `trace_id` once at construction, so every span belongs to the right document trace without threading `trace_id` through every method call.

---

## Layer 2: Within-document concurrency

The pipeline has eight stages today, all sequential:

```
text_extraction → summarize (new) → classify → schema_build → extract → ground+verify → integrate → vectorize → ready
```

### Dependency graph (real, not invented)

| Stage | Depends on |
|-------|------------|
| text_extraction | (start) |
| **summarize (new)** | text_extraction (needs raw_text) |
| classify | text_extraction (needs raw_text + page images) |
| schema_build | classify (needs doc_type) |
| extract | schema_build (needs schema), text_extraction (needs text/images) |
| ground+verify | extract (needs values) |
| integrate | extract (needs detected entities) |
| **vectorize** | summarize, extract |
| ready | integrate, vectorize |

### What can run concurrent

After this analysis, here is the actual concurrency:

1. **`summarize` ∥ `classify`** — both depend only on text_extraction. Run together.
2. **`integrate` ∥ `vectorize`** — vectorize needs summary + raw_text + extracted fields (not the integrated entities). Integrate needs extracted entities. They share no write paths (vectorize writes to `chunks`; integrate writes to `entities`, `facts`, `entity_relationships`, `document_entities`). Run together.

That's it for within-document. Other stages are sequentially dependent. The wins look small (two pairs), but classify is the slowest single agent (multimodal Sonnet with image) and summary takes ~1s — running them together saves ~1s. Vectorize takes 2-5s on docs with substantial text; integrate takes 2-4s. Running them together saves another 2-4s.

### New orchestrator shape

```python
async def run(self, doc_id):
    doc = await self.docs_repo.get_by_id(doc_id)
    trace_id = str(doc_id)

    # Stage 1: text extraction (deterministic, sync)
    raw = await self._extract_text(doc, trace_id)
    await self._mark_status(doc, "extracting_text" → "text_extracted")

    # Stage 2 (parallel): summarize + classify
    summary, classification = await asyncio.gather(
        self._summarize(raw, trace_id),
        self._classify(raw, trace_id),
    )
    await self._persist_summary_and_classification(doc, summary, classification)
    await self._mark_status(doc, "classified")

    # Stage 3: schema build (sequential — depends on classification)
    schema = await self._build_schema(classification, raw, trace_id)
    await self._mark_status(doc, "schema_built")

    # Stage 4: extract (sequential)
    extraction = await self._extract_fields(schema, raw, trace_id)
    await self._mark_status(doc, "extracted")

    # Stage 5: ground + verify with adaptive retry loop
    final_extraction = await self._ground_verify_retry(extraction, raw, schema, trace_id)
    await self._mark_status(doc, "verified")

    # Stage 6 (parallel): integrate + vectorize
    await asyncio.gather(
        self._integrate(final_extraction, doc, trace_id),
        self._vectorize(summary, final_extraction, raw, doc, trace_id),
    )
    await self._mark_status(doc, "ready")
```

### Status semantics change slightly

Phase 1's `verified → integrated → vectorized → ready` becomes `verified → ready` with internal parallel work. The status enum stays the same (`integrated` and `vectorized` are reused as **event** stages emitted to `document_pipeline_events`, even though they no longer appear as document.status values). The frontend's pipeline timeline reads events, so the live UI still shows both phases as completing — possibly with overlapping timestamps, which actually demos the parallelism nicely.

### Failure semantics

If `summarize` ∥ `classify` and one fails:
- Cancel the other (`asyncio.gather` propagates first exception by default; we use `return_exceptions=True` and handle).
- If classify fails: pipeline fails. Document goes to `failed`.
- If summarize fails: log, set summary to a deterministic fallback (the field-concatenation summary from Phase 1), continue. Summary is "best-effort enrichment," not load-bearing.

Same for `integrate` ∥ `vectorize`:
- If integrate fails: pipeline fails.
- If vectorize fails: document is marked ready but flagged `metadata->>'vectorization_failed' = 'true'`. A background sweeper re-vectorizes later. (Document is still searchable via BM25.)

---

## Layer 3: Within-agent batching

### The retry loop today (sequential)

If 3 fields need retry, the current implementation re-runs the extractor 3 times (or does it once with `retry_fields=[a,b,c]` — review actual code in `agents/extractor.py`).

Per the state report:
> Retry augmentation is appended inline in `_build_messages()` when `retry_fields` is set.

So today's extractor already accepts a `retry_fields` list and re-extracts all flagged fields in one call. Good — this is already batched within a single retry pass.

### Phase 1.5 addition: ground + verify + retry in one orchestrated loop

Today:
```
extract → verify → (if any need_retry) extract again → store final values (no re-verify)
```

Phase 1.5:
```
extract → ground (deterministic, fast) + verify (LLM, slower) in parallel
       → decide retry budget per field
       → if any retries needed: targeted extract → ground+verify again
       → repeat up to budget, then accept best-effort
```

`ground` runs as a sync function; `verify` runs as an LLM call. They both produce per-field signals. Combining them gives a stronger signal than either alone (deterministic groundedness catches LLM hallucinations the verifier-LLM might miss; verifier catches semantic wrongness groundedness can't see, like a date that's literally in the doc but wrong context).

### Concurrent LLM calls within an agent

Generally avoid. Anthropic rate limits are organization-wide; running 5 concurrent calls per document × 5 concurrent documents = 25 concurrent Anthropic calls. That'll start to throttle. The 5-agent harness must respect rate limits.

### Concurrency cap

Add a process-wide `asyncio.Semaphore` for Anthropic calls (limit = 10). All agent calls go through the wrapped `anthropic_client.messages.create()` which acquires the semaphore. Same for OpenAI embeddings (semaphore = 5).

---

## VocabCache concurrency

VocabCache becomes process-shared (see `D-VOCAB-CACHE-01`). Two requests for the same user that miss cache and both try to load → use `asyncio.Lock` keyed by user_id so only one runs the load; others await the first.

```python
class VocabCacheStore:
    def __init__(self):
        self._cache: dict[UUID, CachedVocab] = {}
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def get(self, user_id, db):
        if (cached := self._cache.get(user_id)) and not cached.expired:
            return cached
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            if (cached := self._cache.get(user_id)) and not cached.expired:
                return cached
            cached = await self._load(user_id, db)
            self._cache[user_id] = cached
            return cached
```

This pattern (cache-aside with per-key lock) is standard. Implement it correctly the first time.

---

## Cross-document race conditions to watch for

After fixing agent singletons, the remaining cross-doc concern is **entity resolution**. If user uploads two docs of the same person at the same time, both classifier+extractor passes detect "Priya Shah" and both knowledge integrators try to create the entity.

### Fix
`entities` table has a constraint on (user_id, canonical_name) — actually it doesn't per the state report, only on user_id+entity_type. Add a unique index on (user_id, lower(canonical_name)) so concurrent creates conflict and one wins. The other's KI run detects the conflict via ON CONFLICT → fetches the existing entity → continues.

But: canonical names can legitimately collide (two unrelated Rahul Sharmas). Better fix:
- KI agent decision (`match_existing` | `create_new` | `uncertain`) stays the source of truth
- DB write uses `INSERT ... ON CONFLICT DO NOTHING RETURNING id` patterns where applicable
- If two concurrent KIs both choose `create_new` for the same name, both inserts succeed (no unique constraint) and we end up with duplicate entities. This is acceptable for Phase 1.5 — we'll add a deduplication sweep in Phase 2.

For Phase 1.5, accept rare duplicate-entity outcomes when uploads truly race; the cost of preventing this exceeds the value. Note it under `KNOWLEDGE-1.5.md` "Gotchas."

---

## Measurement

After parallelism work, the `document_pipeline_events` table will show overlapping timestamps for the parallel stage pairs. To detect regressions:

- Capture `pipeline_total_duration_ms` per document (computed in orchestrator after `ready`)
- Log to `documents.metadata->>'pipeline_total_ms'`
- Dashboard query: avg/p50/p95 across the demo corpus

Targets in `06-PERFORMANCE-TARGETS.md`.

---

## Things explicitly NOT parallelized (and why)

- **classifier vs schema_architect**: schema needs doc_type → cannot start before classify finishes
- **extractor vs verifier**: verify needs extracted values → must follow
- **across users in same process**: already concurrent via FastAPI's async handlers + worker's `max_jobs`; no further change needed
- **embedding calls between documents**: each doc batches its own chunks; cross-document batching is a Phase 2 optimization if needed

---

## What this is NOT

This isn't "throw `asyncio.gather` at every step and pray." Each parallel pair was chosen because it has zero shared writes, zero data dependencies, and concrete latency savings. Adding more parallelism without that analysis creates more bugs than it solves.
