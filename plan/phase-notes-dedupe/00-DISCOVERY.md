# 00 — Discovery Findings

This file preserves the Claude Code discovery output verbatim from the original planning session. Read once at session start for context; refer back as needed.

---

## Codebase state at phase start (2026-06-02)

### Pipeline stages
text_extraction → classification → schema_building → extraction → verification → integration (parallel with vectorization) → vectorization → finalization

### Notes (`documents.user_note`)
- Column exists on `documents` table
- POST API (`/api/documents`) accepts `user_note` in payload
- **NEVER consumed** by: pipeline orchestrator, vectorizer, knowledge integrator, frontend rendering
- Frontend dropzone does NOT capture a `user_note` field today
- Document detail page does NOT render notes
- This is dead data right now — Phase A wires it end-to-end

### Entity resolver — `api/app/services/knowledge/entity_resolver.py`
- `resolve_and_persist` calls `entities_repo.find_candidates` with trigram threshold **0.3** (set in repository)
- Decision branches: `match_existing` (update aliases + identifiers), `create_new` (insert), `uncertain` (silently inserts as new — line ~102, no flag, no queue, no logging)
- The `uncertain` path is the **primary duplicate source** today

### Knowledge integrator — `api/app/agents/knowledge_integrator.py`
- `KnowledgeIntegratorInput` fields: `document_type`, `detected_entities`, `extracted_fields`, `existing_entities`
- `existing_entities` items sent to LLM include only: `id`, `entity_type`, `canonical_name`, `aliases`, `identifiers`
- NO `relationships`, NO `linked_doc_types`, NO `known_dob`
- The KI prompt's matching rule 3 ("strong name similarity + shared family relationships → match") is **dead code** — the LLM cannot apply it because no relationship data is sent

### DB query notes
- `entities` table has columns: `id, user_id, entity_type, canonical_name, aliases (jsonb), attributes (jsonb), identifiers (jsonb), created_at, updated_at`
- **`deleted_at` does NOT exist on `entities`** — Phase F must add it
- `documents.metadata` column exists (jsonb) but is currently unused
- `documents.full_text_tsv` is computed from `original_filename + summary` (NOT `user_note`)

### Frontend state
- `web/components/upload/dropzone.tsx` — no notes textarea, no `user_note` field sent
- `web/components/document/document-detail-page.tsx` — no notes panel; `loadDocument` does `select("*")` so the column comes back but is ignored in render
- `web/components/graph/graph-page.tsx` — graph view exists with EntitySidePanel; no merge UI

### Demo corpus state (DB not queried during planning)
- UNMEASURED: total entities, total likely-duplicate pairs, uncertain decision rate

### Backend services missing
- No `MentionParser`
- No `DuplicateDetector`
- No `EntityMergeService`
- No `entity_duplicate_candidates` table
- No `note_entity_mentions` table
- No `name_metaphone` column
- No metaphone library installed

### Where note re-integration should sit
- New FastAPI endpoint `/note-reintegrate` (not in `/enqueue`, not in main pipeline)
- Performs only: load note → parse mentions → resolve entities → update `note_entity_mentions` → re-vectorize note chunk
- Does NOT trigger text extraction, classification, field extraction, verification

---

## Constraints carried into design

1. **`uncertain` path must preserve signal** — original plan said "create + flag"; revised plan writes `entity_duplicate_candidates` rows pairing the new entity against KI's considered candidates, with `confidence=0.5` and `reason='ki_uncertain'`. This preserves what KI was uncertain about.
2. **`@mention` resolution must reuse `entity_resolver.resolve_and_persist()`** — no parallel resolution path. Dedupe protections apply.
3. **All `FROM entities` queries must filter `deleted_at IS NULL`** — audit task ND-D-05 enumerates these.
4. **Chunk index convention** — note uses `chunk_index = 0`, body chunks shift by 1. Documented in `02-NOTES-DESIGN.md` and `KNOWLEDGE.md`.

---

## Open items for first-day measurement

Before Phase D implementation begins, capture baseline:
- Run a SQL query to count: pairs of entities with `similarity(canonical_name) > 0.5` that are separate. This is the ground truth for "duplicates that exist today."
- Count `uncertain` decisions in `document_pipeline_events` for the last 30 days (if logged) — establishes current rate.
- Record in `KNOWLEDGE.md` under "Performance baseline."
