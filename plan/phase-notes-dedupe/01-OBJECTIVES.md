# 01 — Objectives

## Headline goals

### A. User notes as first-class signals

Enable users to attach a free-text note to any document — at upload time or by editing it later. The note:
- Is stored on `documents.user_note` (column already exists)
- Flows into the knowledge integrator as explicit context, biasing entity resolution
- Is vectorized as a high-weight chunk (with resolved entity names embedded) at `chunk_index = 0`, making it retrievable in semantic search
- Supports `@EntityName` inline mentions that link to existing entities (no silent auto-create — see Notes Design §"`@mention` resolution")
- Supports `#tag` tagging stored in `documents.metadata.tags`
- Appears in chat retrieval — when a user asks about an entity, source documents whose notes mention that entity surface

### B. Entity deduplication

Prevent, detect, merge, and backfill duplicate entities in the knowledge graph.

- **Prevention:** improve `find_candidates` matching (phonetic, DOB cross-ref, linked doc types) and give the knowledge integrator richer candidate context (relationships, doc types, known DOB) so it chooses `match_existing` correctly more often. The `uncertain` decision now writes `entity_duplicate_candidates` rows preserving the KI's considered candidates — never silently lost.
- **Detection:** a background sweep that finds likely-duplicate clusters and writes them to a `entity_duplicate_candidates` table (using `MAX(existing, new)` so confidence only goes up across re-scans).
- **Merge:** an API endpoint and minimal UI to consolidate two entities. Explicit fact-conflict semantics: winner-wins on conflict, but inherit loser's value when winner has no value for that field.
- **Backfill:** a one-time, idempotent script with a `--max-auto-merges-per-run` safety cap (default 10) that runs the detection sweep on the existing graph, auto-merges very-high-confidence pairs incrementally, and surfaces the rest in a CLI report.

---

## Why this phase

### Notes
At the end of Phase 1.5, the knowledge graph contains extracted facts but has no user voice. A passport for "Aditya Kumar Sharma" has no way to record that this is a sibling, not the account holder. This ambiguity forces every resolution to rely on identifier matches alone; any document without a PAN or passport number creates uncertain entities or duplicates. Notes break this deadlock: "this is my sister's Aadhaar" is a one-line instruction that unambiguously resolves the entity and the relationship.

### Dedupe
The trigram threshold in `find_candidates` is 0.3 — candidates are shown to the LLM but the `uncertain` decision silently creates a new entity instead of preserving the signal. The KI prompt's rule 3 ("shared family relationships → match") is dead code because the candidate context sent to the LLM contains no relationship data. The result: for person entities without hard identifiers, every new document almost certainly creates a duplicate, and the LLM's uncertainty signal is thrown away on every occurrence.

---

## Success criteria

| Criterion | How we verify |
|---|---|
| Upload modal has a notes textarea | Manual UX check; textarea sends `user_note` in POST |
| Document detail page has editable notes panel | Manual UX check; PATCH saves and re-triggers integration |
| Note text appears in chat semantic search results | Chat query for a phrase from a note returns the document |
| Note chunk includes resolved entity names in embedded text | Inspect chunk record: text contains "Entities mentioned: <names>" |
| `@EntityName` mention via autocomplete confirmation creates a `document_entities` row with role `mentioned_in_note` | DB query after upload |
| `@text` without autocomplete confirmation does NOT create an entity (stored as unresolved mention) | DB query: no new entity, note text preserved verbatim |
| Note context in KI prompt reduces `uncertain` decisions for person entities | Before/after counts on demo corpus |
| `uncertain` decisions write `entity_duplicate_candidates` rows pairing the new entity against KI's candidates | DB query after a deliberately-ambiguous upload |
| Detection sweep finds known duplicate pair in demo corpus | CLI script output |
| Sweep re-runs are idempotent and confidence is monotonic | Run twice; row count unchanged; no confidence values went down |
| Merge API consolidates two entities; loser is soft-deleted; fact conflicts follow declared semantics | DB state after merge call; specific fact-conflict test cases |
| Backfill script is idempotent (safe to run twice) | Run twice; second run reports 0 new auto-merges |
| Backfill respects `--max-auto-merges-per-run` cap | Run without override on a graph with > 10 high-confidence pairs; only 10 merged |
| All `FROM entities` reads filter `deleted_at IS NULL` (audit) | Grep + code review; merged entities never appear in chat answers |
| Four required Langfuse spans exist for new paths | Tracing audit (ND-H-04): trace tree shows `note_reintegration`, `mention_resolution`, `dedupe_sweep`, `entity_merge` |
| `pytest -q` passes 100% | CI |
| `pnpm typecheck` passes 100% | CI |

---

## Demo moments (end of phase)

**What the user can do at end of phase that they cannot do today:**

1. **Upload with context:** Drop a file, type "This is my mother @Sunita Sharma's income tax return for FY 2024", upload → graph immediately shows the existing "Sunita Sharma" entity linked to the new document via `mentioned_in_note`. No new duplicate created; the autocomplete pick guaranteed the match.

2. **Edit note after upload:** On the document detail page, click the notes panel → type `@Sunita Sharma — updated PAN card`, save → system runs targeted note re-integration → existing "Sunita Sharma" entity gains the new doc link, no new duplicate created.

3. **Note-powered chat:** Ask "What documents mention my mother?" → chat returns the income tax return and the PAN card, citing the notes as the source of the connection.

4. **Duplicate cleanup:** Admin CLI `python -m app.scripts.dedupe_backfill --dry-run` shows "Sunita Sharma" (2 documents) and "Sunita S." (1 document) flagged as 94% confidence duplicate → user approves → merge → single "Sunita Sharma" entity, 3 documents linked. The merge inherits "Sunita S."'s known DOB (winner had none).

5. **Graph clarity:** After merge, the graph shows one node for "Sunita Sharma" (size proportional to 3 documents) instead of two overlapping nodes. The merged entity does not reappear in any chat answer.

6. **Trace clarity:** Open Langfuse → see four new spans (`note_reintegration`, `mention_resolution`, `dedupe_sweep`, `entity_merge`) for the operations above.
