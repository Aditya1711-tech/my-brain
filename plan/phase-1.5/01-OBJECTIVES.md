# 01 — Phase 1.5 Objectives

## What Phase 1.5 is

A focused **optimization, hardening, and intelligence** phase. No new product features. Five days. We make Phase 1's harness production-grade so that Phase 2 (financial intelligence) builds on a foundation that is fast, correct, and observable.

## What Phase 1.5 is NOT

- Not a financial-domain phase (that's Phase 2)
- Not a re-design — the architecture from Phase 1 stays
- Not a UI overhaul — UI changes only where defects demand them (chat history, retry visibility)
- Not a refactor for refactor's sake — every change has a measurable target

## The four headline goals

### 1. Make every step fast
- Pipeline end-to-end: ≤ 35 s p50, ≤ 60 s p95 per document (down from current ≈ 90+ s sequential)
- Single document chat first token: ≤ 1.5 s p50
- Cross document chat first token: ≤ 2.5 s p50
- Search resolve: ≤ 80 ms p50 across users with ≤ 200 entities
- See `06-PERFORMANCE-TARGETS.md` for the complete SLO table

### 2. Parallelize the independent
The current pipeline runs strictly sequential (no `asyncio.gather` anywhere — confirmed by the state report). Phase 1.5 introduces controlled, safe concurrency:
- **Within a document**: text extraction and image rendering overlap; verifier's retry chain can extract multiple fields in one call instead of N sequential calls; vectorization runs concurrent with knowledge integration
- **Across documents**: keep arq's `max_jobs=5` but **fix the singleton concurrency bug** that makes this unsafe today
- See `03-PARALLELISM-DESIGN.md`

### 3. Self-healing, adaptive harness
- Verifier outputs **per-field retry budget**, not a global hardcoded `MAX_RETRY_COUNT=2`. A high-importance field that scored 0.5 gets up to 3 retries; a low-importance field that scored 0.85 gets 0 retries; a sensitive field (PAN, passport) gets stricter thresholds.
- A new **groundedness check** runs after extraction: every extracted value must appear in or be derivable from `raw_text`. Ungrounded fields are demoted to confidence 0 and re-extracted with a "you hallucinated this" feedback prompt.
- LLM API calls get **transient-error retry with backoff** (currently missing — also confirmed by state report)
- The orchestrator can **resume from any committed status** without losing in-memory state (currently, `_last_extraction` is in-memory and lost on worker restart)
- See `04-SELF-HEALING-HARNESS.md`

### 4. KG + vector hybrid chat (true fusion)
Per your clarification: not "KG with vector as fallback" — **both sources, smartly combined**.
- Question routing decides whether a question is **factual** (KG-heavy), **semantic** (vector-heavy), or **mixed** (both equally)
- The retriever queries KG (entities, facts, relationships) AND vector chunks in parallel
- A **fusion step** merges them: KG facts become high-authority context; relevant chunks become evidence/quotes
- Citations cover both: facts cite the source document; chunks cite chunk_id
- Conversation history is preserved across turns (Phase 1 chat is one-shot)
- See `05-HYBRID-CHAT.md`

## Cleanup objectives (clearing Phase 1 backlog)

From `02-DEFECT-LEDGER.md`. Headline items:

- **Concurrency bug**: agents are module-level singletons with mutable state → race condition under `max_jobs=5`
- **Auth gap**: `/search` and `/chat` accept `user_id` in body with no JWT verification → security hole
- **Stateless chat**: every turn cold-start, no follow-ups possible
- **KG keyword matching**: `_kg_lookup` does substring match on entity names; no semantic understanding, no relationship traversal
- **`retry_count` bug**: increments on the first verifier pass instead of on actual retry → effective max retries is 1, not 2
- **VocabCache thrash**: rebuilt from 7 SQL queries on every search call
- **No tests**: zero test coverage; `pytest` collects 0 tests today
- **Pipeline non-resumable**: `_last_extraction` in-memory state lost on worker restart
- **No LLM API retry**: timeouts and 5xx errors fail the document
- **Deterministic "summary"**: documents.summary is a `field: value;` concatenation, not an LLM summary
- **Empty `/api/folders`, `/api/tags`, `/api/graph` BFF routes**: frontend hits Supabase directly, bypassing planned BFF pattern (low priority — works, but inconsistent)
- **Defect ledger contains 15+ items total** — see `02-DEFECT-LEDGER.md` for the full list with file:line refs

## What does NOT change in Phase 1.5

- The **5-agent harness shape**: still classifier → schema architect → extractor → verifier → knowledge integrator (+ deterministic vectorization). The agents themselves get smarter; the harness shape is preserved.
- The **data model** is preserved except for **additive** columns/tables (see `02-DEFECT-LEDGER.md` for the additive migration list — e.g., `extracted_fields.is_grounded`, `extracted_fields.retry_budget`, `chat_threads`, `chat_messages`).
- **Folder structure** and **coding standards** from Phase 1 are preserved.

## Why these four goals and not others

The state report surfaced ~15 defects of varying severity. We could fix all of them, or we could pick the ones that matter most for Phase 2 readiness. The four goals above are the **load-bearing** ones:

- Phase 2 will multiply throughput (a CAS or bank statement is bigger and more multi-page than a passport). **Performance must scale before more document types arrive.**
- Phase 2 financial data is unforgiving — a wrong account balance or holding is worse than a wrong passport number. **Hallucination guardrails must be in place.**
- Phase 2's value proposition is "ask anything about my financial life" — that requires the KG to be the authoritative answer source. **Hybrid chat must work before financial data lands in the graph.**
- Phase 2's surface area is large. **Parallelism and self-healing buy headroom** for that scale.

Lower-priority items (mobile responsive, demo seeding, deterministic summary improvement) are kept on the ledger but not blocking goals. They get done if there's room; they don't block tag-out.

## Demo target at end of Phase 1.5

A 90-second clip showing:
1. **Upload 5 documents simultaneously.** All complete in < 45 s. Pipeline timelines visibly run in parallel across docs and within docs.
2. **Open Langfuse trace.** Show the new groundedness check span. Show the per-field retry decisions with adaptive budgets.
3. **Ask a factual question** ("what's my wife's passport expiry date?") — answer comes back instantly, cites the source doc, traces through KG facts + relationship traversal.
4. **Ask a semantic question** ("what was the doctor's recommendation in my last report?") — answer comes back from chunks with citations.
5. **Ask a mixed question** ("which family member's passport is expiring soonest?") — answer comes back from KG fact comparison + chunks for context. Shows hybrid fusion working.
6. **Follow up** to that question without re-asking context — proves chat history works.

## Success criteria for Phase 1.5 to be considered complete

See `00-RULES-1.5.md` "Quality bar at end of Phase 1.5" — every bullet must hold.

## Time budget

5 days, 4–5 hours per day = 20–25 working hours. Distributed across tracks for parallel execution. See `07-EXECUTION-PLAN-1.5.md` for the per-day plan and `08-PARALLEL-TRACKS-1.5.md` for parallel orchestration.
