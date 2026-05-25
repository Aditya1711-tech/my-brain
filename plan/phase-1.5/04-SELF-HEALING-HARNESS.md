# 04 — Self-Healing Harness

The Phase 1 harness has hardcoded retry counts (and an off-by-one bug making the effective max 1), no groundedness check, and no recovery from worker crashes or transient LLM failures. Phase 1.5 makes the harness adaptive and resilient.

## Three new capabilities

1. **Per-field adaptive retry budget** — verifier decides how many retries each field deserves based on confidence, importance, and history
2. **Deterministic groundedness check** — extracted values verified against `raw_text` before they reach the LLM verifier
3. **Transient-failure recovery** — LLM API retries, worker-crash resumability, OOM safety

---

## 1. Adaptive retry budget

### Today
- `MAX_RETRY_COUNT = 2` (global constant)
- `retry_count` bug means effective max is 1
- Every flagged field gets the same retry budget
- No notion of "this field is critical, try harder" vs "this field is nice-to-have, skip if not clear"

### Phase 1.5

Verifier output gets a new field per verification entry:

```python
class FieldVerification(BaseModel):
    field_name: str
    confidence: float
    needs_retry: bool
    retry_budget: int       # NEW: how many more retries this field warrants (0-3)
    importance: Literal["critical", "important", "nice_to_have"]  # NEW
    reasoning: str
```

`retry_budget` is set by the verifier based on:

| Confidence | Importance | retry_budget |
|------------|------------|--------------|
| ≥ 0.85 | any | 0 (accept) |
| 0.6–0.84 | critical | 2 |
| 0.6–0.84 | important | 1 |
| 0.6–0.84 | nice_to_have | 0 (accept low-conf) |
| < 0.6 | critical | 3 |
| < 0.6 | important | 2 |
| < 0.6 | nice_to_have | 1 |

The schema architect annotates fields with `importance` (defaults to `important`; sensitive identifiers like passport_number/account_number become `critical`; optional descriptive fields are `nice_to_have`).

### Orchestrator loop

```python
async def _ground_verify_retry(self, extraction, raw_text, schema, trace_id):
    fields = extraction.fields
    iteration = 0
    max_iterations = 4  # absolute ceiling — prevents loops

    while iteration < max_iterations:
        iteration += 1

        # 1. Groundedness check (sync, fast)
        ground_results = check_groundedness(fields, raw_text, schema)

        # 2. Verifier (LLM, slower) — runs only on not-already-clearly-grounded fields
        candidates_for_verify = [f for f in fields if ground_results[f.name].is_grounded or ground_results[f.name].is_ambiguous]
        verify_results = await self.verifier.run(VerifierInput(
            extracted_fields=[f.model_dump() for f in candidates_for_verify],
            schema_fields=schema.fields,
            text_sample=raw_text[:16000],
        ), trace_id=trace_id)

        # 3. Combine signals → final per-field confidence + decision
        combined = combine_signals(ground_results, verify_results, schema)

        # 4. Persist intermediate state
        await self.fields_repo.persist_verification(fields, combined)

        # 5. Decide retries
        to_retry = [name for name, decision in combined.items()
                    if decision.retry_budget_remaining > 0]
        if not to_retry:
            break

        # 6. Retry extractor on flagged fields only
        retry_feedback = build_retry_feedback(combined, to_retry, ground_results)
        retry_output = await self.extractor.run(
            ExtractorInput(
                schema_fields=schema.fields,
                document_type=schema.document_type,
                text=raw_text[:8000],
                retry_fields=to_retry,
                retry_feedback=retry_feedback,
            ),
            page_images=self._page_images,  # passed as arg now
            trace_id=trace_id,
        )

        # 7. Merge retried values into fields list
        fields = merge_fields(fields, retry_output.fields)
        # Decrement remaining budget per retried field
        for name in to_retry:
            combined[name].retry_budget_remaining -= 1

    return fields, combined
```

Total max iterations is capped at 4 (absolute cycle limit) even if individual budgets sum higher. This protects against pathological loops.

### Persisting the new shape

Additive migration:
```sql
ALTER TABLE extracted_fields
  ADD COLUMN importance TEXT,
  ADD COLUMN retry_budget INT DEFAULT 0,
  ADD COLUMN retry_budget_remaining INT DEFAULT 0,
  ADD COLUMN is_grounded BOOLEAN,
  ADD COLUMN groundedness_method TEXT;  -- 'exact_substring' | 'normalized' | 'fuzzy_date' | 'fuzzy_identifier' | 'unground' | 'na'
```

`retry_count` still exists but is reset to 0 at the start of the loop and incremented only on actual retries (fixing `D-RETRY-01`).

---

## 2. Groundedness check

### Purpose
Deterministically verify that each extracted value is actually present in the source document. Catches hallucinations the verifier LLM might rationalize as correct.

### Module

`api/app/services/pipeline/groundedness.py`

```python
@dataclass
class GroundResult:
    field_name: str
    is_grounded: bool
    is_ambiguous: bool   # value is short/common — substring match alone is unreliable
    method: str          # which check passed/failed
    matched_excerpt: str | None  # where in text the value matched

def check_groundedness(fields, raw_text, schema) -> dict[str, GroundResult]:
    results = {}
    normalized_text = normalize_text(raw_text)
    for f in fields:
        if f.value is None or f.value == "":
            results[f.name] = GroundResult(f.name, is_grounded=True, is_ambiguous=False, method="na", matched_excerpt=None)
            continue
        schema_field = find_schema_field(schema, f.name)
        results[f.name] = _check_one(f, schema_field, raw_text, normalized_text)
    return results
```

### Per-type matchers

```python
def _check_one(field, schema_field, raw, normalized):
    value = field.value
    ftype = schema_field.field_type

    if ftype == "identifier":
        # Try exact, then strip spaces/hyphens, then with separators
        for variant in identifier_variants(value):
            if variant.lower() in normalized:
                return GroundResult(field.name, True, False, "identifier_normalized", excerpt_around(raw, variant))
        return GroundResult(field.name, False, False, "unground", None)

    if ftype == "date":
        # Try ISO, DD/MM/YYYY, MM/DD/YYYY, DD-Mon-YYYY, written-out month
        for variant in date_variants(value):
            if variant in raw or variant.lower() in normalized:
                return GroundResult(field.name, True, False, "fuzzy_date", excerpt_around(raw, variant))
        return GroundResult(field.name, False, False, "unground", None)

    if ftype == "currency_amount" or ftype == "number":
        # Strip commas, currency symbols; try with and without decimals
        for variant in number_variants(value):
            if variant in raw or variant in normalized:
                return GroundResult(field.name, True, False, "number_normalized", excerpt_around(raw, variant))
        return GroundResult(field.name, False, False, "unground", None)

    if ftype == "enum":
        if value.lower() in normalized:
            return GroundResult(field.name, True, False, "enum_lower", None)
        # Enum is ambiguous if value is very short
        return GroundResult(field.name, False, len(value) < 4, "unground", None)

    # default: string
    if value.lower() in normalized:
        is_ambiguous = len(value) < 4   # 2-3 char values are too common
        return GroundResult(field.name, True, is_ambiguous, "string_substring", excerpt_around(raw, value))
    # Try normalized (collapse whitespace, remove punct)
    if _aggressive_normalize(value) in _aggressive_normalize(raw):
        return GroundResult(field.name, True, False, "string_normalized", None)
    return GroundResult(field.name, False, False, "unground", None)


def normalize_text(s: str) -> str:
    # lowercase, collapse whitespace, remove non-alphanumeric except basic punctuation
    return re.sub(r"\s+", " ", s.lower().strip())


def identifier_variants(v: str) -> list[str]:
    base = v.strip()
    return list(set([base, base.upper(), base.lower(), base.replace(" ", ""), base.replace("-", ""), base.replace(" ", "").replace("-", "")]))


def date_variants(v: str) -> list[str]:
    # Parse v, then format in multiple common variants. If parse fails, return [v]
    ...
```

### Combining with verifier signals

`combine_signals(ground, verify, schema)`:

```python
def combine_signals(ground, verify, schema):
    out = {}
    for field in schema.fields:
        name = field.name
        g = ground.get(name)
        v = verify.fields_by_name.get(name)

        # If field is not grounded → confidence is capped at 0.3 regardless of verifier
        if g and not g.is_grounded and not g.is_ambiguous:
            confidence = min(v.confidence if v else 0.3, 0.3)
            importance = v.importance if v else "important"
            retry_budget = _compute_budget(confidence, importance) + 1  # extra +1 for ungrounded
            out[name] = FieldDecision(confidence, importance, retry_budget, retry_budget, reason="ungrounded")
            continue

        # If ambiguous (short value), trust verifier more
        if g and g.is_ambiguous:
            confidence = (v.confidence if v else 0.5) * 0.9  # mild penalty
            ...

        # Default: ground + verify agree → use verifier confidence
        out[name] = FieldDecision(...)
    return out
```

### Effect

A hallucinated passport number (well-formed but not in the doc) becomes:
- `ground.is_grounded = False` → confidence capped at 0.3, retry budget +1
- Retry prompt includes: "Value 'A1234567' was not found in the source — re-examine and try again"
- After retry: either correct value (now grounded) or pipeline accepts low confidence and flags for UI review

---

## 3. Transient-failure recovery

### LLM API retries

Add to `api/app/utils/retry.py`:

```python
from anthropic import APIStatusError, APIConnectionError
from openai import APIStatusError as OpenAIStatusError, APIConnectionError as OpenAIConnError

TRANSIENT_ANTHROPIC = (APIConnectionError, asyncio.TimeoutError)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

def is_transient_error(exc):
    if isinstance(exc, (APIConnectionError, OpenAIConnError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, (APIStatusError, OpenAIStatusError)):
        return exc.status_code in TRANSIENT_STATUS_CODES
    return False

async def with_retry(coro_factory, *, max_attempts=3, base=1.0, cap=8.0):
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            if not is_transient_error(exc) or attempt == max_attempts:
                raise
            backoff = min(cap, base * (2 ** (attempt - 1)))
            jitter = random.uniform(0, backoff * 0.2)
            logger.warning("llm_retry", attempt=attempt, sleep=backoff+jitter, error=repr(exc))
            await asyncio.sleep(backoff + jitter)
```

Apply in clients:

```python
# integrations/anthropic_client.py
class AnthropicClient:
    async def messages_create(self, **kwargs):
        return await with_retry(lambda: self._client.messages.create(**kwargs))
```

Same for `openai_embeddings.py`.

### Worker-crash resumability

The orchestrator's `_last_extraction` (RawExtraction with page_images) is in-memory and lost on worker restart.

Fix: persist what's needed to resume.

**Option A — store page images in Supabase Storage at extraction time.** When `pdf.py` renders page images, upload them to `<user_id>/<doc_id>/page_images/<n>.png`. On resume, load them from Storage.

**Option B — store a `processing_state` JSONB column on documents** with everything needed for resumption (image URLs, current schema, intermediate field extractions).

Recommended: **A + B**. Page images live in Storage (might be large; cheap to fetch on resume). Lightweight state (schema, current extraction outputs) lives in `documents.processing_state`.

```sql
ALTER TABLE documents ADD COLUMN processing_state JSONB DEFAULT '{}'::jsonb;
```

The orchestrator updates `processing_state` after each significant step:

```python
async def _persist_state(self, doc_id, key, value):
    await self.db.execute(text("""
        UPDATE documents
        SET processing_state = processing_state || jsonb_build_object(:key, :value::jsonb),
            updated_at = now()
        WHERE id = :doc_id
    """), {"doc_id": str(doc_id), "key": key, "value": json.dumps(value)})
```

On pipeline resume, the orchestrator hydrates from `processing_state` first. If empty (fresh run), it runs from scratch.

### OOM and timeout safety

- The arq job timeout is 300s. Documents that legitimately need longer (massive PDFs) currently fail. Phase 1.5: bump to 600s, log a warning if pipeline approaches the timeout.
- Page images for very long PDFs can blow memory if all loaded in process. Limit to first 5 pages for extractor multimodal (already in place per state report). For docs > 50 pages, also reduce image DPI on render.

---

## What gets traced

Every Phase 1.5 addition becomes a Langfuse span:
- `groundedness_check` span — per-field results as metadata
- `retry_loop` parent span containing iterations
- Each `retry_iteration_N` span with the fields retried
- LLM retry attempts as nested spans with attempt number

This is the "wow moment" demo: open the trace tree, see groundedness running before verifier, see adaptive retries with reasoning per field. Phase 1's trace tree is good; Phase 1.5's tells a story.

---

## What does NOT change

- Agent prompts (other than the verifier prompt, which now needs to emit `retry_budget` and `importance` — small additions)
- Anthropic SDK usage pattern (still tools/tool_choice with structured output)
- The orchestrator's overall stage sequence (text → summarize/classify → schema → extract → ground+verify+retry → integrate/vectorize → ready)
- Pydantic models for ExtractionOutput, ClassifierOutput, etc. (only Verifier's output schema changes)

---

## Phase 2 forward-compat

Financial docs in Phase 2 will introduce new value types — Decimal amounts, ISIN codes, account numbers. The groundedness check's per-type matcher pattern extends naturally: add `_check_isin`, `_check_account_number`. The `importance` annotation will be heavily used in finance: a wrong account balance is critical; a wrong "remarks" field is nice-to-have.
