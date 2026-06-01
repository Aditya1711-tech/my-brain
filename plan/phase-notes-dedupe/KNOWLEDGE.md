# KNOWLEDGE — Phase: Notes + Entity Dedupe

Living decisions + gotchas log. Updated at milestones.

---

## Phase start state (2026-06-02)

### Codebase state inherited from Phase 1.5

- Pipeline stages: text_extraction → classification → schema_building → extraction → verification → integration (parallel with vectorization) → vectorization → finalization
- `user_note` column exists on `documents` table and is accepted by the POST API, but is NEVER consumed by pipeline, vectorizer, integrator, or frontend
- Trigram threshold in `find_candidates`: **0.3** (too permissive)
- KI `uncertain` decision → silently creates new entity (core duplicate source; KI's reasoning signal is lost)
- KI candidate context: only `id, entity_type, canonical_name, aliases, identifiers` — no relationships, no doc types
- KI prompt rule 3 ("shared family relationships → match") is dead code because candidates don't include relationship data
- No `@mention` parsing, no notes panel in frontend, no note-to-entity linking
- `entities.deleted_at` does NOT exist yet (added in ND-A-01)
- No metaphone, no DOB cross-reference, no linked doc-type signal in candidate matching

### Key architectural decisions made during planning

**1. Keep `documents.user_note` as single-value (not `document_notes` table)**
Rationale: This is a single-user app; note is a current intent, not an audit log. History is implicit via facts versioning. Revisit if multi-user annotation is added.

**2. Note as dedicated chunk at `chunk_index = 0` (LOCKED CONVENTION)**
Note chunk uses `chunk_index = 0`. Body chunks start at `chunk_index = 1`. If document has no note, skip 0 and start body at 1. Reasoning: positive integers avoid the "bug-looking `-1`" smell; `0` for note sorts first in `ORDER BY chunk_index ASC`. This convention is project-wide and not negotiable.

**3. Note chunk text composition includes resolved entity names (LOCKED FORMAT)**
The note chunk's text is:
```
Note: {user_note}
Entities mentioned: {comma-separated names, or "none"}
Document: {filename} ({doc_type})
```
Embedding resolved entity names in the text gives the chunk strong semantic recall for entity-name queries ("show me Sunita's documents"). Notes alone embed poorly for that pattern.

**4. `uncertain` path preserves signal via `entity_duplicate_candidates`**
Original design: "create entity + needs_review flag." Revised: create entity AND write `entity_duplicate_candidates` rows pairing the new entity against each KI-considered candidate, with `confidence=0.5` and `reason='ki_uncertain'`. The KI's signal — *which candidates it considered* — is never lost. The sweep picks these up immediately on its next run rather than re-discovering the duplication from raw name similarity. Drops the need for a separate `entity_resolution_queue` table.

**5. `@mention` does NOT auto-create entities**
A bare `@text` in a note creates nothing — it's stored as unresolved text. Only when the user explicitly picks "Create new entity: X" from autocomplete does an entity get created, and that creation routes through `entity_resolver.resolve_and_persist()` so dedupe protections apply. Prevents typos from polluting the graph.

**6. Note re-integration uses targeted path, not full pipeline re-run**
Editing a note should not cost 30+ seconds of LLM calls. Only: parse mentions → resolve entities via `entity_resolver` → re-vectorize note chunk (chunk_index=0 only). Raw text chunks stay unchanged.

**7. Merge fact-conflict semantics: winner-wins on conflict, but inherit blanks from loser**
When merging B into A:
- A has value + B has none → keep A's (no change)
- A has no value + B has value → **inherit B's value as A's current fact**
- Both have values → keep A's current, archive B's with `valid_until = now()`
Why: simple "winner wins" loses partial data the loser had (e.g., a DOB the winner never knew).

**8. Sweep confidence is monotonic across re-runs**
`entity_duplicate_candidates` UPSERT uses `MAX(existing.confidence, new.confidence)`. Re-runs never reduce confidence. Prevents the case where a previously-flagged duplicate disappears because the latest scan scored it lower (different data state).

**9. Backfill has a safety cap by default**
`dedupe_backfill --max-auto-merges-per-run` defaults to 10. Forces operator awareness before bulk auto-merging. Combined with `--dry-run`, gives a safety ladder: dry-run → run with cap 10 → review → raise cap.

**10. `auto_merge_eligible` at 0.95 confidence**
High bar intentional. At 0.95, false positives should be near zero. For 0.7–0.95 pairs, human review is required.

**11. Both tracks must agree on `KnowledgeIntegratorInput` shape before implementing**
The agreed final shape is in `05-PARALLEL-TRACKS.md`. Neither track may deviate without updating that file.

**12. `deleted_at IS NULL` filter is mandatory on all `entities` reads**
Audit task ND-D-05 enumerates every file that reads from `entities` and ensures the filter is added. Regression test seeds a soft-deleted entity and asserts it's invisible in graph, chat, autocomplete, and search.

### Observability for new paths (LOCKED)

Four Langfuse spans MUST exist by end of phase. Audit in ND-H-04.

| Span name | Where | Metadata |
|---|---|---|
| `note_reintegration` | `routes/note_reintegrate.py` top-level | `doc_id`, `mention_count` |
| `mention_resolution` | `services/notes/mention_resolver.py` | input mentions list, output entity_ids |
| `dedupe_sweep` | `services/knowledge/duplicate_detector.py` top-level | `user_id`, pair counts by confidence bucket |
| `entity_merge` | `services/knowledge/entity_merge_service.py` top-level | `winner_id`, `loser_id`, summary (facts_inherited, facts_archived, etc.) |

These are demo-critical — the "look at the trace tree" moment for this phase depends on them.

---

## Performance baseline (before this phase)

To be measured at start of implementation session (before ND-A-01):
- `uncertain` decision rate on demo corpus: UNMEASURED
- Duplicate entity pairs in demo corpus: UNMEASURED (DB not accessible during planning)
- Pipeline end-to-end time (upload to ready): UNMEASURED (carried from Phase 1.5 — check `/plan/phase-1.5/KNOWLEDGE-1.5.md`)
- Number of documents with `user_note IS NOT NULL` (for ND-G-02 sizing): UNMEASURED

---

## Performance targets (end of phase)

- `uncertain` decision rate: < 15% of person-type entities (down from estimated ~40% without note context and richer candidates)
- Note chunk vectorization overhead: < 200ms added to pipeline
- Note re-integration latency (PATCH → done): < 5s
- Merge API latency: < 500ms for a typical merge (< 50 facts, < 20 documents)
- Backfill script runtime: < 60 seconds for a 1000-entity graph
- Dedupe sweep monotonic invariant: always (re-run never reduces confidence)

---

## Agents and services added

| Name | Location | Purpose |
|---|---|---|
| `MentionParser` | `api/app/services/notes/mention_parser.py` | Parse `@mention` and `#tag` tokens from notes |
| `MentionResolver` | `api/app/services/notes/mention_resolver.py` | Write `note_entity_mentions` rows; for new-entity picks routes through `entity_resolver.resolve_and_persist()` |
| `TagParser` | `api/app/services/notes/tag_parser.py` | Parse `#tag` tokens, write to `documents.metadata.tags` |
| `DuplicateDetector` | `api/app/services/knowledge/duplicate_detector.py` | Detection sweep algorithm with MAX confidence UPSERT |
| `DuplicateCandidatesRepo` | `api/app/repositories/duplicate_candidates_repo.py` | UPSERT helpers for `entity_duplicate_candidates` |
| `EntityMergeService` | `api/app/services/knowledge/entity_merge_service.py` | Transactional merge with fact-conflict resolution; returns summary |

---

## API endpoints added or changed

| Method | Path | Status | Notes |
|---|---|---|---|
| PATCH | `/api/documents/:id/note` | New (web BFF) | Updates `user_note`, resets `user_note_indexed_at`, refreshes TSV |
| POST | `/note-reintegrate` | New (FastAPI) | Targeted note re-integration; uses `entity_resolver` for new entity picks |
| POST | `/entities/merge` | New (FastAPI) | Merge two entities; returns summary dict |
| POST | `/api/entities/merge` | New (web BFF) | Forwards to FastAPI merge endpoint |

---

## Gotchas / watch out for

1. **`knowledge_integrator.md` merge conflict** — both tracks touch this file. Always merge manually; never auto-resolve.
2. **`note_entity_mentions` UNIQUE constraint** — `(document_id, entity_id)` — re-running note integration must UPSERT, not INSERT, to avoid constraint violations.
3. **Full-text TSV update** — `user_note` must be included in TSV re-computation whenever the note changes. Update TSV in the PATCH endpoint (or via trigger).
4. **`deleted_at` on entities** — does NOT exist before ND-A-01. Migration adds it. Audit task ND-D-05 ensures all reads filter it.
5. **`uncertain` decisions in backfill** — entities involved in `entity_duplicate_candidates` rows with `reason='ki_uncertain'` are the most likely duplicate sources; they're already flagged for the sweep, so backfill catches them on first run.
6. **Note chunk index = 0** — LOCKED. Body chunks shift to start at index 1. Vectorizer must enforce this convention; queries that assumed chunk_index 0 was a body chunk need updating (audit during ND-B-01).
7. **Autocomplete query rate** — the `@mention` autocomplete fires on every keystroke. Debounce 200ms client-side to avoid flooding Supabase.
8. **Autocomplete deleted_at filter** — autocomplete queries on entities MUST include `.is("deleted_at", null)` — otherwise merged entities reappear as suggestions.
9. **`entity_resolver` shared edits** — Track A adds `user_note` parameter; Track B modifies the `uncertain` branch. These touch different parts of the same file. Track B's ND-D-04 should land first.
10. **Sweep idempotency requires MAX rule** — naive UPSERT (overwriting confidence) can cause regressions when later scans see less data than earlier scans. The `MAX(existing, new)` rule is non-negotiable.
11. **Backfill safety cap** — default of 10 is intentional. Operators MUST explicitly raise the cap for larger graphs. Documented in `--help`.
12. **Mention resolver bypassing `entity_resolver` is FORBIDDEN** — When creating an entity from a "Create new entity: X" pick, the resolver MUST route through `entity_resolver.resolve_and_persist()` so dedupe (find_candidates, KI, etc.) still applies. Bypass would create a parallel entity-creation path that defeats this phase's purpose.

---

## Prior phase doc corrections

(none found during discovery)
