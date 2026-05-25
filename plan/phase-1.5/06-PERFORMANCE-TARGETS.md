# 06 — Performance Targets

The contract for "fast." Every Phase 1.5 task that claims a perf improvement must measure against these.

## SLO table

| Operation | p50 | p95 | Notes |
|-----------|-----|-----|-------|
| Pipeline end-to-end per document (single, average size — 3 page PDF) | ≤ 25 s | ≤ 45 s | down from baseline ≈ 60-90 s |
| Pipeline end-to-end (5 concurrent documents) | ≤ 35 s | ≤ 60 s | per document, not total |
| Pipeline stage: `text_extraction` | ≤ 1.5 s | ≤ 3 s | for digital PDF up to 10 pages |
| Pipeline stage: `summarize` ∥ `classify` (parallel) | ≤ 4 s | ≤ 7 s | runs together |
| Pipeline stage: `schema_build` | ≤ 3 s | ≤ 6 s | |
| Pipeline stage: `extract` | ≤ 5 s | ≤ 12 s | multimodal Sonnet with up to 5 page images |
| Pipeline stage: `ground+verify+retry` (one iteration) | ≤ 3 s | ≤ 6 s | groundedness is sub-ms; verifier is the cost |
| Pipeline stage: `integrate` ∥ `vectorize` (parallel) | ≤ 5 s | ≤ 10 s | |
| Search resolve (user with ≤ 200 entities, warm cache) | ≤ 80 ms | ≤ 200 ms | |
| Search resolve (cold cache) | ≤ 250 ms | ≤ 500 ms | only first request per user, per 60s TTL |
| Single-doc chat — first token | ≤ 1.5 s | ≤ 2.5 s | embedding + retrieve + Sonnet stream start |
| Cross-doc chat — first token | ≤ 2.5 s | ≤ 4 s | router + parallel retrievers + Sonnet stream start |
| Per-document cost (avg) | ≤ $0.10 | — | sum across all agent calls |
| Per-document cost (worst single doc) | ≤ $0.20 | — | excluding rare 3+ retry cases |

These are p50/p95 over the **demo corpus** (10 documents covering 5 different doc types) processed on Railway's standard instances.

## Pre-Phase 1.5 baseline

Capture **before** any optimization work. First task on Day 1 is to run a baseline benchmark and record numbers in `KNOWLEDGE-1.5.md` under "Performance log."

Baseline procedure:
1. Reset demo user's data
2. Upload the 10-document fixture set, one at a time (sequential)
3. Record `document_pipeline_events.duration_ms` for each stage per doc
4. Upload the same set, all at once (concurrent, max_jobs=5)
5. Record again
6. Run 20 search queries, record p50/p95
7. Run 10 chat questions (5 single-doc, 5 cross-doc), record first-token p50/p95
8. Insert all numbers into `KNOWLEDGE-1.5.md` under "Performance log → Baseline"

## After each optimization

Re-run the same benchmark. Record numbers in `KNOWLEDGE-1.5.md` under "Performance log → After <task-id>". Include the **delta** in the commit message:

```
perf(pipeline,phase-1.5): parallelize summarize+classify (-1.1s p50)

Before: avg 8.4s for summarize+classify combined sequential
After:  avg 4.2s with asyncio.gather
Measured across 10-doc demo corpus on Railway instance.
```

## Measurement infrastructure

### Per-stage durations
Already captured in `document_pipeline_events.duration_ms`. Phase 1.5 adds:
- Total pipeline duration → `documents.metadata->>'pipeline_total_ms'` (set when status → 'ready')
- Total cost → `documents.metadata->>'pipeline_total_cost_usd'` (sum across agents)

### Per-agent token usage
Already logged via `structlog`. Phase 1.5 also persists in `document_pipeline_events.details`:
```json
{ "input_tokens": 1234, "output_tokens": 567, "model": "claude-sonnet-4-6" }
```

### Chat latency
New table or metadata field:
```sql
ALTER TABLE chat_messages ADD COLUMN first_token_ms INT;
ALTER TABLE chat_messages ADD COLUMN total_ms INT;
ALTER TABLE chat_messages ADD COLUMN cost_usd NUMERIC(10,6);
```

Captured per assistant message.

### Search latency
Log per request with structlog; not persisted. For benchmark, use a hot loop and capture from logs.

### Benchmark script
`scripts/bench_phase_1_5.py` — single command that:
- Sets up demo user state
- Uploads the 10-doc fixture
- Runs the search and chat suites
- Outputs a markdown table to stdout
- Appends to `KNOWLEDGE-1.5.md` under "Performance log"

## Regression policy

**No PR merges to main if any p95 exceeds its SLO** unless the PR description includes a justification + tracking issue. We don't want to ship something fast on Tuesday and slow on Friday.

Phase 1.5 sessions running the benchmark at end-of-day catch drift.

## What we are NOT measuring

- Per-user dashboard load time (frontend) — not in scope; Phase 2 has time to optimize
- Long-tail OCR latency on scanned multi-language PDFs — not in baseline corpus; covered in Phase 1.5 only opportunistically
- Embedding API latency variance — assume within normal range; OpenAI's stability is acceptable

## Cost guardrails

- Per-document cost target ≤ $0.10 (Phase 1 doc said this; still applies)
- Chat cost target ≤ $0.01 per turn
- If a document exceeds $0.20 cost, log a warning and surface in monitoring (not strictly an SLO; an investigative trigger)

## Hardware assumption

Targets assume Railway "standard" instances for both API and worker. If you upgrade plans, document the change in `KNOWLEDGE-1.5.md` and re-baseline.

## Demo corpus

10 documents stored under `tests/fixtures/demo_corpus/`:
1. `passport_self.pdf` — clean PDF, digital
2. `passport_spouse.pdf` — clean PDF, digital
3. `marriage_certificate.pdf` — scanned, mid-quality
4. `birth_certificate_child.pdf` — scanned, mid-quality
5. `xray_report.pdf` — text-heavy report PDF
6. `salary_slip.pdf` — tabular layout
7. `invoice.pdf` — invoice with line items
8. `presentation.pptx` — 8 slides
9. `spreadsheet.xlsx` — financial summary, 30 rows
10. `id_card.jpg` — phone photo of an ID card

Document procurement: synthetic / anonymized real / publicly licensed. The corpus lives in git as a fixture; no real PII committed.
