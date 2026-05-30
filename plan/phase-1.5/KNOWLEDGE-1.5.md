# KNOWLEDGE-1.5 — Living state (Phase 1.5)

Update after each milestone or non-trivial decision. Sessions resume by reading this and `PROGRESS-1.5.md`.

---

## Phase 1.5 current state

> What's deployed for Phase 1.5, what's working, what's pending.

- **Status:** Day 1 in progress (4/7 tasks done)
- **Deployed:** Phase 1 (`v1.0-phase-1`) on main + production
- **Done:** SETUP-01 (bootstrap), BENCH-01 (baseline), HARNESS-01 (D-AGENT-01 singleton fix), HARNESS-02 (D-RETRY-01 retry_count fix)
- **In progress:** HARNESS-03 (LLM API retry with backoff)
- **Remaining Day 1:** SETUP-02 (test harness), SETUP-03 (merge + tag)

## Decisions made

> Format: short title — date — decision — reasoning. Append, don't remove.

### 2026-05-25 — Phase 1.5 scope locked
Decision: limit Phase 1.5 to four headline goals (speed, parallelism, self-healing, hybrid chat) + defect ledger cleanup. No financial features.
Reasoning: Phase 2 is large; foundations must be production-grade before adding more surface area.

### 2026-05-25 — Postgres + JSONB for processing_state, not new table
Decision: persist pipeline mid-run state in `documents.processing_state` JSONB column rather than a new table.
Reasoning: simpler, no extra RLS surface, fits the additive-migration principle.

### 2026-05-25 — TTL-only VocabCache, no Redis invalidation
Decision: 60s TTL, no invalidation pub/sub.
Reasoning: simplicity; new entities visible to search within 60s is acceptable for personal use.

### 2026-05-25 — KG + Vector run in parallel always (not fallback)
Decision: both retrievers always execute; fusion layer decides weights based on routing hint.
Reasoning: user feedback — "smartly combine both sources." Fallback model was rejected.

### 2026-05-25 — JWT verification only on /search /chat (not /enqueue)
Decision: /enqueue keeps X-API-Key shared secret; /search and /chat use Supabase JWT.
Reasoning: /enqueue is server-to-server from Next.js BFF; /search and /chat could be hit by user-facing clients directly.

## Performance log

> Baseline + after-each-task snapshots. Source of truth for whether SLOs are met.

### Baseline (pre-Phase-1.5)

Captured 2026-05-25, 5 documents (passport ×2, aadhaar ×2, trade licence ×1).

| Metric | p50 | p95 | Mean | SLO target |
|--------|-----|-----|------|------------|
| **Pipeline total (sum of stages)** | **112.4 s** | **198.0 s** | **132.7 s** | ≤ 25 s p50 / ≤ 45 s p95 |
| Text Extraction | 3.5 s | 40.5 s | 10.0 s | ≤ 1.5 s / ≤ 3 s |
| Classification | 5.5 s | 6.3 s | 5.2 s | (part of parallel group) |
| Schema Building | 11.7 s | 14.4 s | 12.0 s | ≤ 3 s / ≤ 6 s |
| Extraction | 25.3 s | 28.6 s | 22.9 s | ≤ 5 s / ≤ 12 s |
| Verification | 33.3 s | 46.2 s | 33.2 s | ≤ 3 s / ≤ 6 s |
| Integration | 42.6 s | 48.2 s | 35.0 s | ≤ 5 s / ≤ 10 s |
| Vectorization | 3.9 s | 6.9 s | 4.5 s | (part of parallel group) |

**Key findings:**
- Every stage exceeds its SLO. Total pipeline is ~4.5× over target.
- Integration (35s mean) and Verification (33.2s mean) are the top bottlenecks.
- Extraction (22.9s mean) is 4× over target — multimodal Sonnet call dominates.
- Schema Building (12s mean) is 4× over target.
- Text Extraction is fast for digital PDFs (2-5s) but 69.7s for the scanned Trade Licence.
- Classification is the cheapest LLM stage at ~5s.
- Wall-clock times showed large gaps vs sum for some docs, indicating queue or retry delays.

### After Day 1
_TBD_

### After Day 2
_TBD_

### After Day 3
_TBD_

### After Day 4
_TBD_

### Final (Phase 1.5 close)
_TBD_

## Schema state

> Migrations applied during Phase 1.5. Additive only unless ledger says otherwise.

- `0003` (2026-05-26): `extracted_fields` + `is_grounded`, `groundedness_method`, `importance`, `retry_budget`, `retry_budget_remaining`; `documents` + `processing_state` JSONB

- `0004` (2026-05-30): `chat_threads` (scope, document_id, title) + `chat_messages` (thread_id, role, content, citations JSONB) + RLS on both

### Pending migrations
_(none)_

## API endpoints added or changed

> Append as work lands. Format: `METHOD /path — change — owner track`.

_(none yet)_

## Agents and services added

- [ ] `agents/summarizer.py` — Haiku-based document summary
- [ ] `services/pipeline/groundedness.py` — deterministic field-vs-text check
- [ ] `services/chat/router.py` — question intent + routing classification
- [ ] `services/chat/kg_retriever.py` — entity + fact + relationship retrieval
- [ ] `services/chat/fusion.py` — KG + chunk fusion + reranker
- [ ] `services/chat/thread_repo.py` — chat thread/message persistence
- [ ] `utils/retry.py` — transient-error retry with backoff

## Dependencies added beyond Phase 1

> One-line justification per addition.

_(none yet)_

## Gotchas discovered

> Tribal knowledge from doing the work.

_(none yet — append as found)_

## Phase 1 doc corrections

> Errors in Phase 1 plan files found during Phase 1.5 work. We do not edit Phase 1 docs; log here and the human reviews later.

_(none yet)_

## Test fixtures

> Sample documents used in tests. Path + purpose.

- `tests/fixtures/demo_corpus/passport_self.pdf` — _to be added_
- `tests/fixtures/demo_corpus/passport_spouse.pdf` — _to be added_
- `tests/fixtures/demo_corpus/marriage_certificate.pdf` — _to be added_
- `tests/fixtures/demo_corpus/birth_certificate_child.pdf` — _to be added_
- `tests/fixtures/demo_corpus/xray_report.pdf` — _to be added_
- `tests/fixtures/demo_corpus/salary_slip.pdf` — _to be added_
- `tests/fixtures/demo_corpus/invoice.pdf` — _to be added_
- `tests/fixtures/demo_corpus/presentation.pptx` — _to be added_
- `tests/fixtures/demo_corpus/spreadsheet.xlsx` — _to be added_
- `tests/fixtures/demo_corpus/id_card.jpg` — _to be added_

All fixtures must be anonymized or synthetic. No real PII in repo.

## Demo account

> Reset before any live demo.

- **Email:** TBD
- **Password:** TBD
- **Seeded with:** demo_corpus fixtures

## Cost telemetry

- **Per-document target:** ≤ $0.10
- **Per-document Phase 1 baseline:** TBD (capture in baseline benchmark)
- **Per-document Phase 1.5 actual:** TBD

- **Chat per-turn target:** ≤ $0.01
- **Chat per-turn baseline:** TBD
- **Chat per-turn Phase 1.5 actual:** TBD

## Open questions

> Things to validate with the human before assuming.

_(none yet)_

## Phase 2 preview (do not build)

> Notes accumulated about financial phase. Carry forward at Phase 1.5 close.

- Financial domain: CAS, salary slips, CC bills, insurance, MF statements, GST docs
- Will reuse: entity model (person + organization + asset + holding), fact versioning, KG retriever, hybrid chat
- Will add: net worth aggregation, portfolio overlap math, tax position tracking, insurance audit
- Phase 1.5 hooks ready: importance levels (critical fields like account_balance), groundedness for numbers/currency, chat routing intent for "compare"

## Phase 1.5 completion log

> One entry per day completed. Date + 3-line summary.

_(none yet)_
