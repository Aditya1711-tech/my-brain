# 04 — Execution Plan

Task IDs follow the format `ND-<phase>-<seq>` where phase ∈ {A, B, C, D, E, F, G, H}.

Each task lists: subject, files touched, verification step, estimated time, dependencies.

---

## Phase A — Notes capture + storage

### `ND-A-01` DB migration — notes + dedupe schema (45 min)
**Shared dependency for both tracks. Must land on `main` first.**

- New columns: `documents.user_note_indexed_at timestamptz`, `entities.name_metaphone text`, `entities.deleted_at timestamptz`
- New indices: `idx_entities_metaphone` (partial, on metaphone NOT NULL), `idx_entities_active` (partial, on `deleted_at IS NULL`)
- New tables: `note_entity_mentions`, `entity_duplicate_candidates`
- RLS policies on new tables (4 each: select/insert/update/delete by user_id = auth.uid())
- TSV expression updated to include `user_note` (drop+recreate trigger or generated column)

**Files:** new migration file under `api/migrations/versions/`
**Verify:** `alembic upgrade head` succeeds; `\d note_entity_mentions` and `\d entity_duplicate_candidates` show expected columns; RLS enabled on both
**Depends on:** nothing

### `ND-A-02` Upload UI — notes textarea in dropzone (45 min)
- Add textarea component to `dropzone.tsx` with 2000-char limit + counter
- Include `user_note` in the POST body to `/api/documents`
- Help text: "Use @Name to link to people, #tag to tag" (note: upload-time mentions stay unresolved until edited in document detail)

**Files:** `web/components/upload/dropzone.tsx`
**Verify:** Drop a file, type a note, upload; DB row for document has `user_note` populated
**Depends on:** none (just a UI field; backend already accepts it)

### `ND-A-03` Document detail — editable notes panel (75 min)
- Add a panel between summary card and extracted fields
- Read mode: render note with resolved `@mention` as chips, unresolved `@text` as muted text, `#tags` as tag chips
- Edit mode: textarea with Save/Cancel; calls PATCH endpoint on Save
- Loading state during re-integration

**Files:** `web/components/document/document-detail-page.tsx`, possibly a new `web/components/document/notes-panel.tsx`
**Verify:** Edit a note, save, see "Re-processing…" then "Saved"; reload and verify content persists
**Depends on:** ND-A-05 (PATCH endpoint)

### `ND-A-04` `@mention` autocomplete in note panel (60 min)
- Listen for `@` character → open autocomplete dropdown
- Query Supabase directly: `.from("entities").select("id, canonical_name").is("deleted_at", null).ilike("canonical_name", "%query%")`
- Show up to 5 existing entity suggestions
- Show "Create new entity: <typed>" option when ≥2 chars typed (only after the `@`)
- Debounce 200ms client-side
- On pick: write the mention as a "resolved" token in the textarea (with a hidden entity_id attribute or special marker)
- On unrecorded user dismiss (escape, click outside): mention stays unresolved
- Same pattern for `#` tag autocomplete

**Files:** new `web/components/shared/mention-autocomplete.tsx`, used in `notes-panel.tsx`
**Verify:** Type `@Sun`, see suggestions; pick one → chip renders; type `@xyz` and dismiss → plain `@xyz` text; type `#tax`, see existing tags
**Depends on:** ND-A-03

### `ND-A-05` PATCH /api/documents/:id/note BFF endpoint (45 min)
- Zod validates `{ user_note: z.string().max(2000) }`
- Auth check (user owns document)
- Updates `documents.user_note`, resets `user_note_indexed_at = NULL`
- Refreshes `full_text_tsv` (manually within the same query)
- Calls FastAPI `POST /note-reintegrate` with `{ doc_id }`
- Returns `{ ok: true }`

**Files:** `web/app/api/documents/[id]/note/route.ts`
**Verify:** PATCH with a note → DB shows `user_note` updated, `user_note_indexed_at` NULL; tsv contains note words
**Depends on:** ND-A-01 (migration); ND-B-04 (FastAPI endpoint can be stubbed initially)

---

## Phase B — Notes integrated into harness

### `ND-B-01` Vectorizer — include note in composition (45 min)
- Load `user_note`, resolved mention names (via JOIN to `note_entity_mentions` and `entities` with `deleted_at IS NULL`), filename, doc_type
- If `user_note` non-empty: emit a dedicated chunk at `chunk_index = 0` with the locked format from `02-NOTES-DESIGN.md`
- Body chunks start at `chunk_index = 1` (shift existing logic by 1)
- If `user_note` empty: skip 0 entirely, start body at 1

**Files:** `api/app/services/pipeline/vectorizer.py`
**Verify:** Process a document with a note; query `SELECT chunk_index, text FROM chunks WHERE document_id = X ORDER BY chunk_index` and confirm chunk 0 is the note in the locked format, chunk 1+ is body
**Depends on:** ND-A-01

### `ND-B-02` Orchestrator — load `user_note` in `_integrate` (20 min)
- Modify the SELECT in `_integrate` to include `user_note`
- Pass `user_note` to `resolver.resolve_and_persist()`

**Files:** `api/app/services/pipeline/orchestrator.py`
**Verify:** Add a log line printing the user_note length passed to KI; upload doc with note; verify log
**Depends on:** ND-B-03

### `ND-B-03` `KnowledgeIntegratorInput` — add `user_note` + prompt update (45 min)
- Add `user_note: str | None = None` field to `KnowledgeIntegratorInput`
- Update KI prompt (`api/app/agents/prompts/knowledge_integrator.md`) with the note section
- **Coordinate with Track B on prompt edits** — see `05-PARALLEL-TRACKS.md` "Shared file contract"

**Files:** `api/app/agents/knowledge_integrator.py`, `api/app/agents/prompts/knowledge_integrator.md`
**Verify:** Run KI with a note in input; LLM response references the note context
**Depends on:** Track B's `existing_entities` format change (ND-D-03) MUST land first per contract

### `ND-B-04` FastAPI `/note-reintegrate` endpoint (60 min)
- New route `POST /note-reintegrate { doc_id: UUID }`
- Loads document, parses mentions via mention parser (ND-C-01)
- For confirmed-resolved picks (from the frontend): writes `note_entity_mentions` rows directly
- For "Create new entity from mention" picks: synthesizes a single-entity `detected_entities` payload and calls `entity_resolver.resolve_and_persist()` so dedupe applies
- Re-emits chunk_index=0 (deletes existing, embeds new)
- Sets `user_note_indexed_at = now()`
- Wraps in Langfuse `note_reintegration` span

**Files:** `api/app/routes/note_reintegrate.py` (new), service module under `api/app/services/notes/`
**Verify:** Hit endpoint → DB shows `note_entity_mentions` rows; chunk 0 re-emitted with current content; `user_note_indexed_at` set
**Depends on:** ND-C-01, ND-C-02, ND-B-01

### `ND-B-05` Full-text TSV includes `user_note` (30 min)
- Update the document TSV expression (trigger or generated column) to include `user_note`
- Refresh TSV in PATCH endpoint after `user_note` updates
- Add the `note_match` score boost (+0.3) in search resolver when query matches `user_note`

**Files:** migration (or trigger SQL), `api/app/services/search/resolver.py`
**Verify:** Insert doc with note containing "carnation". Search "carnation" → doc appears in results
**Depends on:** ND-A-01

---

## Phase C — Notes mention parsing + entity linking

### `ND-C-01` `@mention` parser (pure function) (45 min)
- Pure function `parse_mentions(text: str) -> list[Mention]` extracts `@Name` tokens with `char_offset`
- Handles `@Single`, `@With Spaces` (terminated by punctuation, newline, or end), nested quotes (best effort)
- Returns list of (mention_text, char_offset) tuples

**Files:** `api/app/services/notes/mention_parser.py`
**Verify:** Unit tests covering single, multi-word, end-of-string, with-punctuation mentions
**Depends on:** none

### `ND-C-02` Mention resolver → `note_entity_mentions` rows (60 min)
- Service that takes a list of frontend-confirmed mentions + entity_ids and writes `note_entity_mentions` rows
- For "create new" picks: routes through `entity_resolver.resolve_and_persist()` with single-entity payload — dedupe protections apply
- UPSERT on `(document_id, entity_id)` to allow idempotency
- Wraps in Langfuse `mention_resolution` span
- Writes `document_entities` rows with role `mentioned_in_note`

**Files:** `api/app/services/notes/mention_resolver.py`
**Verify:** Idempotency test (call twice with same input, only one row exists); dedupe test (creating "Sunit" when "Sunita" exists with high similarity routes through resolver, doesn't create duplicate)
**Depends on:** ND-C-01

### `ND-C-03` `#tag` parser + storage to `metadata.tags` (30 min)
- Pure function `parse_tags(text: str) -> list[str]`
- Service writes the union of new tags into `documents.metadata.tags` (JSONB array)
- Idempotent (set semantics — duplicates collapse)

**Files:** `api/app/services/notes/tag_parser.py`
**Verify:** Note with `#tax #urgent` → `metadata.tags = ["tax", "urgent"]`. Re-process → still 2 tags. Add #tax_2024 → 3 tags.
**Depends on:** ND-A-01

### `ND-C-04` KG retriever — note mention path (45 min)
- In `kg_retriever.py`, when resolving an entity to retrieve facts, also query `note_entity_mentions` for docs that mention the entity
- Filter `entities.deleted_at IS NULL` in the JOIN
- Return these docs as context alongside fact citations

**Files:** `api/app/services/chat/kg_retriever.py`
**Verify:** Upload doc with note "this is my mother @Sunita Sharma's passport". Ask chat "what documents mention my mother?". Result includes that document.
**Depends on:** ND-A-01

---

## Phase D — Dedupe prevention

### `ND-D-01` `name_metaphone` column + backfill existing entities (45 min)
- Migration: install `metaphone` library (`pip install metaphone` in `requirements.txt`)
- Backfill script computes metaphone for all existing entities (in batches) and updates `name_metaphone`
- New entities compute metaphone on insert (in `entities_repo.create()`)

**Files:** `requirements.txt`, `api/app/repositories/entities_repo.py`, new backfill script `api/app/scripts/backfill_metaphone.py`
**Verify:** All existing entities have non-null metaphone; insert new entity, verify metaphone set
**Depends on:** ND-A-01

### `ND-D-02` Expand `find_candidates` — phonetic + DOB + doc-type (75 min)
- Add phonetic condition (metaphone match)
- Add DOB cross-reference via `facts` subquery
- Add `linked_doc_types` to returned columns via JOIN+GROUP BY
- Raise trigram threshold from 0.3 to 0.5
- Filter `entities.deleted_at IS NULL`

**Files:** `api/app/repositories/entities_repo.py`
**Verify:** Unit tests with seeded data: identical metaphone matches; same DOB matches; trigram below 0.5 doesn't match
**Depends on:** ND-D-01

### `ND-D-03` KI — richer candidate context (relationships + doc_types + DOB) (60 min)
- Batch query for relationships of candidate entities (one query, not N)
- Add `relationships`, `linked_doc_types`, `known_dob` fields to each candidate dict passed to KI
- Update KI prompt's `existing_entities` format section to describe new fields
- **Coordinate with Track A** per `05-PARALLEL-TRACKS.md` "Shared file contract"

**Files:** `api/app/services/knowledge/entity_resolver.py`, `api/app/agents/prompts/knowledge_integrator.md`
**Verify:** Upload a passport for an existing person who has a `child_of` relationship; KI prompt input shows the relationship in candidate context
**Depends on:** ND-A-01

### `ND-D-04` Fix `uncertain` path — write `entity_duplicate_candidates` rows (60 min)
- In `entity_resolver.py`, when KI returns `uncertain`:
  - Still create the new entity (preserve non-blocking behavior)
  - Loop over `considered_candidate_ids` from KI's reasoning context and UPSERT `entity_duplicate_candidates` rows with `confidence=0.5`, `reason="ki_uncertain"`, `ki_reasoning=ki.reasoning`
  - Use canonical ordering (`min(a,b)`, `max(a,b)`) to satisfy the CHECK constraint
- Log a structured event with new_entity_id and considered_count

**Files:** `api/app/services/knowledge/entity_resolver.py`, new `api/app/repositories/duplicate_candidates_repo.py`
**Verify:** Force an `uncertain` decision (mock KI); confirm new entity created AND candidate rows written; re-running pipeline doesn't create new candidate rows (UPSERT)
**Depends on:** ND-A-01

### `ND-D-05` Audit: filter `deleted_at IS NULL` on all entity reads (45 min)
- Grep for `FROM entities` in `api/` and add `AND deleted_at IS NULL` (or appropriate JOIN clause)
- Audit autocomplete queries in frontend (Supabase `.from("entities")` calls) and add `.is("deleted_at", null)`
- Files most likely touched: `entities_repo.py`, `kg_retriever.py`, `search/resolver.py`, `graph-page.tsx`, `mention-autocomplete.tsx`, vectorizer JOINs
- Commit message must list all files touched
- Regression test: seed two entities, soft-delete one, assert it does not appear in: graph view, chat retrieval, autocomplete, search results

**Files:** multiple — list in commit message
**Verify:** Regression test passes; manual smoke confirms merged entities don't appear anywhere
**Depends on:** ND-A-01

---

## Phase E — Dedupe detection

### `ND-E-01` `entity_duplicate_candidates` table (covered in ND-A-01)
Already created in the shared migration. This task is a marker — confirm RLS policies and indices exist.

### `ND-E-02` Detection sweep — `duplicate_detector.py` (90 min)
- Implements the 4 passes (name similarity, shared identifier, shared doc, phonetic)
- UPSERT with MAX(existing, new) confidence
- Sets `auto_merge_eligible = true` for confidence ≥ 0.95
- Skips pairs in status 'merged' or 'dismissed'
- Wraps top-level in Langfuse `dedupe_sweep` span; logs per-pair confidence

**Files:** `api/app/services/knowledge/duplicate_detector.py`
**Verify:** Seed two entities with similar names (e.g., "Sunita Sharma" / "Sunita S."); run sweep; row in `entity_duplicate_candidates` with confidence > 0.7. Re-run; confidence ≥ first run; row count unchanged.
**Depends on:** ND-D-01 (metaphone), ND-A-01

### `ND-E-03` CLI report for duplicate candidates (30 min)
- `python -m app.scripts.dedupe_sweep [--user-id UUID] [--dry-run]`
- Prints summary: total pairs, by confidence bucket, auto-merge eligible count
- `--dry-run` skips persisting (useful for testing)

**Files:** `api/app/scripts/dedupe_sweep.py`
**Verify:** Run script with --dry-run on demo data; verify output format; run without --dry-run; verify DB rows match
**Depends on:** ND-E-02

---

## Phase F — Dedupe merge

### `ND-F-01` `EntityMergeService` — merge in single transaction (90 min)
- Implements the transactional merge per `03-ENTITY-DEDUPE-DESIGN.md` "Merge semantics"
- Fact conflict resolution per the explicit rules table
- Returns summary dict: `{ facts_inherited, facts_archived, docs_transferred, relationships_added }`
- Wraps in Langfuse `entity_merge` span with winner/loser as metadata
- All operations in single transaction; rolls back on any failure

**Files:** `api/app/services/knowledge/entity_merge_service.py`
**Verify:** Unit tests for each fact-conflict case (winner-has-only, loser-has-only, both-have); transaction rollback test (force failure mid-merge, assert no partial state)
**Depends on:** ND-A-01

### `ND-F-02` FastAPI merge endpoint `POST /entities/merge` (30 min)
- Validates auth (user owns both entities)
- Calls `EntityMergeService.merge()`
- Returns summary

**Files:** `api/app/routes/entities.py` (new) or extend existing
**Verify:** Curl with two entity IDs; DB state matches expected; summary in response matches
**Depends on:** ND-F-01

### `ND-F-03` Web BFF + graph UI — "Merge with…" button (60 min)
- Add `web/app/api/entities/merge/route.ts` BFF (auth check + forward)
- Add "Merge with…" button in `EntitySidePanel` of graph page
- Modal with entity search (filtered to `deleted_at IS NULL`)
- Confirmation dialog
- On success: refresh graph; show toast with summary

**Files:** `web/app/api/entities/merge/route.ts`, `web/components/graph/graph-page.tsx`
**Verify:** Click Merge with…; pick target; confirm; graph refreshes; loser node gone; winner node has loser's docs
**Depends on:** ND-F-02

---

## Phase G — Backfill

### `ND-G-01` Backfill script — sweep + auto-merge on existing graph (60 min)
- `python -m app.scripts.dedupe_backfill [--user-id UUID] [--dry-run] [--auto-merge-threshold 0.95] [--max-auto-merges-per-run N]`
- Default `--max-auto-merges-per-run = 10` (safety rail)
- Default `--auto-merge-threshold = 0.95`
- Runs sweep, then auto-merges top-N pairs by confidence descending
- Idempotent

**Files:** `api/app/scripts/dedupe_backfill.py`
**Verify:** Run twice; second run reports 0 auto-merges. Run on demo graph with > 10 high-conf pairs without override; only 10 merged; warning printed about remaining.
**Depends on:** ND-E-02, ND-F-01

### `ND-G-02` Backfill notes on existing documents (30 min)
- One-time script: for each document where `user_note IS NOT NULL AND user_note_indexed_at IS NULL`, call `/note-reintegrate`
- Skip documents with empty user_note
- Idempotent (re-running finds no new docs to process)

**Files:** `api/app/scripts/backfill_notes.py`
**Verify:** Mark a processed doc's `user_note_indexed_at` NULL manually; run script; verify it processes that one doc and sets `user_note_indexed_at`
**Depends on:** ND-B-04

---

## Phase H — Smoke + tracing + benchmark

### `ND-H-01` Smoke test — notes flow end-to-end (45 min)
- Manual end-to-end on demo corpus:
  - Upload doc with note "@Sunita Sharma's passport"
  - Use autocomplete to pick existing Sunita
  - Verify `note_entity_mentions` row exists
  - Verify chunk_index=0 contains note + "Entities mentioned: Sunita Sharma"
  - Ask chat "what documents mention Sunita?" → returns this doc
  - Edit note → trigger re-integration → verify chunk 0 re-emitted
- Document results in PROGRESS.md

**Depends on:** Phases A, B, C

### `ND-H-02` Smoke test — dedupe flow end-to-end (45 min)
- Seed a known duplicate pair in demo data
- Run `dedupe_sweep --dry-run` → confirm pair detected
- Run `dedupe_backfill` without override on a graph with > 10 high-conf pairs → verify cap behavior
- Manually merge via UI → verify graph cleanup
- Re-run sweep → confirm pair no longer surfaces

**Depends on:** Phases D, E, F, G

### `ND-H-03` Final benchmark in KNOWLEDGE.md (30 min)
- Measure: `uncertain` decision rate before/after; note chunk vectorization overhead; merge API latency; backfill runtime
- Record in `KNOWLEDGE.md` under "Performance log"

**Depends on:** ND-H-01, ND-H-02

### `ND-H-04` Tracing audit — verify four required spans exist (30 min)
- Manually run: a note re-integration, a mention resolution, a dedupe sweep, a merge
- Open Langfuse → verify spans exist with appropriate metadata:
  - `note_reintegration` — input doc_id, mention count
  - `mention_resolution` — input mentions list, output entity_ids
  - `dedupe_sweep` — user_id, pair count by bucket
  - `entity_merge` — winner_id, loser_id, summary
- Fix any missing instrumentation
- Document trace examples in `KNOWLEDGE.md`

**Depends on:** Phases B, C, E, F

---

## Performance targets

| Metric | Target |
|---|---|
| `uncertain` decision rate (person entities) | < 15% (down from estimated ~40%) |
| Note chunk vectorization overhead added to pipeline | < 200ms |
| Note re-integration latency (PATCH → done) | < 5s |
| Merge API latency (typical: < 50 facts, < 20 docs) | < 500ms |
| Backfill runtime (1000-entity graph) | < 60s |
| Dedupe sweep monotonic (re-runs never decrease confidence) | Always |

---

## Critical ordering across tracks

- ND-A-01 MUST land first on `main` — both tracks depend on the migration
- ND-D-03 (Track B's KI candidate format change) MUST land before ND-B-03 (Track A's note section append) per the shared-file contract in `05-PARALLEL-TRACKS.md`
- ND-D-05 (audit task) can run in parallel with anything else but MUST be done before ND-H-02 to validate merge cleanliness
- ND-G-01 + ND-G-02 are sequential and run after all of Track B + Track A are merged
