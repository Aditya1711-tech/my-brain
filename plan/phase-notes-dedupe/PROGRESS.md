# PROGRESS — Phase: Notes + Entity Dedupe

**Branch:** `phase-notes-dedupe/main`
**Tag at end:** `v1.2-phase-notes-dedupe`
**Phase start:** 2026-06-02
**Phase status:** IN PROGRESS — ND-A-01 complete; awaiting merge before track work begins

---

## Current

- **Track A:** ND-B-03 (KI input model + prompt — blocked until Track B lands ND-D-03)
- **Track B:** ND-D-02 (expand find_candidates — phonetic + DOB + doc-type)

---

## Track A task tracker (Notes)

| ID | Subject | Status | Closed |
|---|---|---|---|
| ND-A-01 | DB migration — notes+dedupe schema | [x] | 2026-06-02 |
| ND-A-02 | Upload UI — notes textarea in dropzone | [x] | 2026-06-02 |
| ND-A-03 | Document detail — editable notes panel | [x] | 2026-06-02 |
| ND-A-04 | `@mention` autocomplete in note panel (with `deleted_at IS NULL` filter) | [x] | 2026-06-02 |
| ND-A-05 | PATCH /api/documents/:id/note BFF endpoint | [x] | 2026-06-02 |
| ND-B-01 | Vectorizer — note chunk at index 0 with locked format; body chunks shift to index 1+ | [x] | 2026-06-02 |
| ND-B-02 | Orchestrator — load `user_note` in `_integrate` | [x] | 2026-06-02 |
| ND-B-03 | `KnowledgeIntegratorInput` — add `user_note` + prompt section | [ ] | |
| ND-B-04 | FastAPI `/note-reintegrate` endpoint (routes new entities through `entity_resolver`) | [ ] | |
| ND-B-05 | Full-text TSV includes `user_note`; +0.3 note_match score boost | [ ] | |
| ND-C-01 | `@mention` parser (pure function) | [ ] | |
| ND-C-02 | Mention resolver — `note_entity_mentions` rows; routes through `entity_resolver` for new picks | [ ] | |
| ND-C-03 | `#tag` parser + storage to `metadata.tags` | [ ] | |
| ND-C-04 | KG retriever — note mention path (with `deleted_at IS NULL` filter) | [ ] | |

---

## Track B task tracker (Dedupe)

| ID | Subject | Status | Closed |
|---|---|---|---|
| ND-A-01 | DB migration (shared with Track A) | [x] | 2026-06-02 |
| ND-D-01 | `name_metaphone` column + backfill existing entities | [x] | 2026-06-02 |
| ND-D-02 | Expand `find_candidates` — phonetic + DOB + doc-type; threshold 0.3→0.5 | [ ] | |
| ND-D-03 | KI — richer candidate context (relationships + doc_types + known_dob) | [ ] | |
| ND-D-04 | Fix `uncertain` path — preserve KI signal via `entity_duplicate_candidates` rows | [ ] | |
| ND-D-05 | Audit: filter `deleted_at IS NULL` on all entity reads (multi-file commit) | [ ] | |
| ND-E-01 | `entity_duplicate_candidates` table (in ND-A-01) | [x] | 2026-06-02 |
| ND-E-02 | Detection sweep + `duplicate_detector.py` (MAX confidence UPSERT) | [ ] | |
| ND-E-03 | CLI report for duplicate candidates | [ ] | |
| ND-F-01 | `EntityMergeService` — merge in single transaction with fact-conflict rules | [ ] | |
| ND-F-02 | FastAPI merge endpoint `POST /entities/merge` (returns summary) | [ ] | |
| ND-F-03 | Web BFF + graph UI — "Merge with…" button | [ ] | |

---

## Sequential at end

| ID | Subject | Status | Closed |
|---|---|---|---|
| ND-G-01 | Dedupe backfill — sweep + auto-merge on existing graph (with `--max-auto-merges-per-run` cap of 10) | [ ] | |
| ND-G-02 | Notes backfill — `/note-reintegrate` on existing docs with `user_note IS NOT NULL` | [ ] | |
| ND-H-01 | Smoke test — notes flow end-to-end | [ ] | |
| ND-H-02 | Smoke test — dedupe flow end-to-end | [ ] | |
| ND-H-03 | Final benchmark record in KNOWLEDGE.md | [ ] | |
| ND-H-04 | Tracing audit — verify `note_reintegration`, `mention_resolution`, `dedupe_sweep`, `entity_merge` spans | [ ] | |

---

## Recently completed

- 2026-06-02 | ND-A-01 | DB migration — notes+dedupe schema (migration `20260602_0005`; both tables, all columns, RLS, TSV trigger)
- 2026-06-02 | ND-E-01 | entity_duplicate_candidates table marker (created in ND-A-01; RLS + indices confirmed)
- 2026-06-02 | ND-A-02 | Upload UI — notes textarea (shared per-batch, 2000 char limit + counter, user_note in POST body)
- 2026-06-02 | ND-A-05 | PATCH /api/documents/[id]/note BFF — updates user_note, resets indexed_at, calls note-reintegrate (non-blocking)
- 2026-06-02 | ND-A-03 | Document detail — NotesPanel component; read/edit modes; @token+#tag rendering; PATCH on save
- 2026-06-02 | ND-A-04 | MentionAutocomplete — @entity debounced (200ms, deleted_at IS NULL), #tag lazy-load, keyboard nav, resolved_mentions forwarded to PATCH+note-reintegrate
- 2026-06-02 | ND-B-01 | Vectorizer — note chunk at index 0 (locked format: Note+Entities mentioned+Document); body at 1+; single embed batch
- 2026-06-02 | ND-B-02 | Orchestrator: _integrate SELECT now includes user_note; resolver.resolve_and_persist() gets user_note param
- 2026-06-02 | ND-D-01 | metaphone added to requirements.txt; entities_repo.create() computes doublemetaphone primary on insert; backfill_metaphone.py script (batched, --dry-run)

---

## Defects tracker

(none yet — populate as defects are found)

---

## Blockers

(none)

---

## Session log

| Date/Time | Track | Description | Tasks closed | Next up |
|---|---|---|---|---|
| 2026-06-02 | planning | Discovery + initial plan files written | — | Human review |
| 2026-06-02 | planning | Plan revised — 11 design improvements folded in (uncertain signal preservation, chunk index convention, @mention safety, embedded entity names in note chunk, fact-conflict semantics, monotonic confidence, backfill safety cap, deleted_at audit, tracing audit, notes backfill task) | — | Awaiting human approval |
| 2026-06-02 | both | ND-A-01: DB migration 0005 — notes+dedupe schema written; ND-E-01 marker closed | ND-A-01, ND-E-01 | ND-A-02 (Track A), ND-D-01 (Track B) |
| 2026-06-02 | Track A | ND-A-02: dropzone notes textarea + user_note in POST body | ND-A-02 | ND-A-05, ND-D-01 |
| 2026-06-02 | Track A | ND-A-05: PATCH /api/documents/[id]/note BFF; non-blocking note-reintegrate call | ND-A-05 | ND-A-03 |
| 2026-06-02 | Track A | ND-A-03: NotesPanel — read/edit modes, resolved/unresolved @mention rendering, #tag chips | ND-A-03 | ND-A-04 |
| 2026-06-02 | Track A | ND-A-04: MentionAutocomplete — entity search, #tag autocomplete, resolved_mentions forwarded to PATCH | ND-A-04 | ND-B-01 |
| 2026-06-02 | Track A | ND-B-01: vectorizer — note chunk (locked format) at index 0; body at 1+; mention names in note embedding | ND-B-01 | ND-B-02 |
| 2026-06-02 | Track A | ND-B-02: orchestrator _integrate loads user_note; resolver signature extended; log line added | ND-B-02 | ND-D-01→D-03 then ND-B-03 |
| 2026-06-02 | Track B | ND-D-01: metaphone in requirements.txt; entities_repo.create() computes+stores metaphone; backfill_metaphone.py script | ND-D-01 | ND-D-02 |
