# 02 — Notes Design

## Data model

### Decision: keep `documents.user_note` (single-value), do NOT add `document_notes` table

**Rationale:**

The per-document note is a *current intent* field, not an audit log. The use case is "I want to tell the system what this document is / who it belongs to." That is a single, mutable value — editing it replaces the previous note. History is preserved implicitly because facts have a `valid_from`/`valid_until` pattern and the graph state before the edit remains in `facts`/`entity_relationships`.

A `document_notes` table would add value only if:
- Multiple users annotate the same document (not in scope — this is a single-user app)
- We need a note history audit trail (not requested)
- We need threaded comments (not requested)

**Conclusion:** `documents.user_note text` is sufficient. No schema migration needed for this column — it already exists.

### New column: `documents.user_note_indexed_at`

We need to know whether the current note has been processed by the pipeline (for re-integration after edits). Add:

```sql
ALTER TABLE documents ADD COLUMN user_note_indexed_at timestamptz;
```

Semantics: NULL = not yet processed or note has changed since last processing. Set to `now()` after note integration completes. When the note is edited (PATCH), reset to NULL → triggers background re-integration.

### New table: `note_entity_mentions`

Stores the structured `@EntityName` links parsed from a note:

```sql
CREATE TABLE note_entity_mentions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    mention_text text NOT NULL,           -- the raw @Name text
    char_offset  integer,                 -- position in note for future highlighting
    created_at   timestamptz DEFAULT now(),
    UNIQUE (document_id, entity_id)       -- one mention row per entity per doc
);
CREATE INDEX idx_note_entity_mentions_entity ON note_entity_mentions(entity_id);
CREATE INDEX idx_note_entity_mentions_doc    ON note_entity_mentions(document_id);
```

This table powers:
- Autocomplete: "which entities have already been mentioned in notes?" → suggest them for `@` completions
- Retrieval: when chat resolves entity X, find docs with `note_entity_mentions.entity_id = X` to surface as sources
- Graph edges: notes can explicitly assert a relationship ("this is my mother") that becomes a `entity_relationships` row

---

## Chunk index convention (LOCKED — do not change)

The note chunk uses `chunk_index = 0`. All other chunks for the document start at `chunk_index = 1` and increment from there. This is a project-wide convention applied during vectorization.

Rationale: `-1` looks like a bug to future readers; positive integers are unambiguous. `0` for the note also positions it first in any `ORDER BY chunk_index ASC` query.

Update the existing vectorizer to:
- Reserve `chunk_index = 0` for the note (if present)
- Start body chunks at `chunk_index = 1`
- If the document has no note: skip 0 and start body at `chunk_index = 1` (do NOT use 0 for a body chunk — `0` is exclusively reserved for "this is a note chunk")

---

## Inline mention syntax

### `@EntityName` resolution (LOCKED — autocomplete-confirmed only)

**Resolution model:** Notes contain free-form `@text` strings. These do NOT automatically create entities. Only when the user explicitly confirms a "Create new entity: X" option from the autocomplete dropdown does an entity get created.

Two mention states:

1. **Resolved mention** — the user picked an existing entity from autocomplete, OR explicitly confirmed creation of a new one. A row is written to `note_entity_mentions` and `document_entities` (role: `mentioned_in_note`). UI renders as a chip/pill with the entity's canonical name.

2. **Unresolved mention** — the user typed `@text` without picking from autocomplete (e.g., they typed fast, hit space, moved on). The text is stored verbatim in the note. No entity is created. No DB row written. UI renders as plain `@text` (or a muted/grey style).

The note remains fully searchable in both cases (full-text TSV includes `user_note`). The difference is structural linking — only resolved mentions create graph edges.

**Resolution algorithm (only applied when user clicks an autocomplete result):**

- If user picked an existing entity: use that entity_id directly. Write `note_entity_mentions` row. Add to `document_entities` with role `mentioned_in_note`.
- If user picked "Create new entity: X": call `entity_resolver.resolve_and_persist()` with a synthesized `detected_entities` payload containing one entity (name = X, type = `person` by default, role = `mentioned_in_note`). This routes through the standard dedupe machinery — `find_candidates` runs, KI decides, dedupe protections apply. The mention then references whatever entity ID the resolver returned.

**Why route through `resolve_and_persist()`:** A user who typed `@Sunit` and confirmed "Create new entity: Sunit" should still benefit from dedupe — if "Sunita" already exists with high similarity, the standard resolver may match it (or flag uncertainty via `entity_duplicate_candidates`). Never build a parallel entity-creation path that bypasses dedupe — see also `00-RULES.md` forbidden actions and `03-ENTITY-DEDUPE-DESIGN.md`.

### `#tag` syntax

- Syntax: `#` followed by a tag slug (no spaces; underscores allowed)
- Stored as array in `documents.metadata` (already a jsonb column, currently unused) under key `"tags"`
- Example: `{"tags": ["tax_2024", "urgent", "mother"]}`
- Tags are indexed in full-text search (add to `full_text_tsv` expression) and exposed as a search facet
- Tags do NOT create entity links (tags are document-level, not entity-level)

---

## Notes flow into knowledge integrator

### Change to `KnowledgeIntegratorInput`

Add `user_note: str | None` field. Final shape per `05-PARALLEL-TRACKS.md`:

```python
class KnowledgeIntegratorInput(BaseModel):
    document_type: str
    detected_entities: list[dict]
    extracted_fields: list[dict]
    existing_entities: list[dict]   # Track B adds: relationships, linked_doc_types, known_dob
    user_note: str | None = None    # Track A adds (this section)
```

### Change to `api/app/agents/prompts/knowledge_integrator.md`

Add a section at the top (before "Matching rules"):

```
If a user note is present (see "User note" below), treat it as the highest-priority signal
for entity resolution. A note like "this is my mother's passport" means the document holder
MUST be resolved to an existing entity named with a maternal relationship to the user, or
a new entity created with that semantic tag. The note overrides name-only uncertainty.
```

And append to the input section:

```
## User note
{{user_note if present, else "No note provided."}}

If the note contains @Name references, treat those as hard matches — the user is asserting
which entity the document belongs to. @Name references take precedence over extracted name
similarity alone.
```

### Change to `_integrate` in `orchestrator.py`

```python
# Load doc data — add user_note to SELECT
result = await self.db.execute(
    sql_text("SELECT raw_text, schema_json, doc_type, user_note FROM documents WHERE id = :doc_id"),
    {"doc_id": str(doc.id)},
)
row = result.fetchone()
doc_type = row[2] or "unknown" if row else "unknown"
user_note = row[3] if row else None

# Pass user_note through to resolver
await resolver.resolve_and_persist(
    user_id=doc.user_id,
    document_id=doc.id,
    document_type=doc_type,
    detected_entities=detected_entities,
    extracted_fields=extracted_dicts,
    user_note=user_note,         # NEW
    trace_id=trace_id,
)
```

---

## Notes feed the vectorizer

### Change to `api/app/services/pipeline/vectorizer.py`

Load `user_note` alongside `summary` and resolved mentions:

```python
result = await db.execute(
    sql_text("""
        SELECT d.raw_text, d.summary, d.user_note, d.original_filename, d.doc_type
        FROM documents d
        WHERE d.id = :doc_id
    """),
    {"doc_id": str(doc_id)},
)
row = result.fetchone()
raw_text  = row[0] or "" if row else ""
summary   = row[1] or "" if row else ""
user_note = row[2] or "" if row else ""
filename  = row[3] or "" if row else ""
doc_type  = row[4] or "unknown" if row else "unknown"

# Load resolved entity names from note mentions
mention_names = []
if user_note.strip():
    m_result = await db.execute(
        sql_text("""
            SELECT e.canonical_name
            FROM note_entity_mentions nem
            JOIN entities e ON e.id = nem.entity_id
            WHERE nem.document_id = :doc_id AND e.deleted_at IS NULL
        """),
        {"doc_id": str(doc_id)},
    )
    mention_names = [r[0] for r in m_result.fetchall()]
```

### Note chunk text composition (LOCKED format)

When `user_note` is non-empty, emit a dedicated chunk at `chunk_index = 0` with this exact text composition:

```
Note: {user_note}
Entities mentioned: {comma-separated resolved entity names, or "none" if no resolved mentions}
Document: {original_filename} ({doc_type})
```

Including resolved entity names in the embedded text gives the chunk strong semantic recall for queries like "show me Sunita's documents" — the embedding carries both user words and structural entity names.

### Body chunks

Body chunks start at `chunk_index = 1`. Existing composition for body chunks is unchanged:

```python
parts = []
if summary:
    parts.append(f"Summary: {summary}")
if field_pairs:
    parts.append("Extracted fields: " + "; ".join(field_pairs))
if raw_text:
    parts.append(raw_text)
# Note is also prepended to full_text for context continuity in body chunks
if user_note.strip():
    parts.insert(0, f"Note: {user_note}")
```

**Weight reasoning:** The note is user-authored, deliberately chosen, and highly precise. Emitting it as a dedicated chunk with embedded entity names ensures it has an independent embedding that scores high on entity-name queries and doesn't get diluted by raw_text noise.

### Note re-vectorization after edit

When a note is edited (PATCH /api/documents/:id/note):
1. Delete the existing chunk where `chunk_index = 0` for this document (if it exists)
2. Re-emit a new chunk at `chunk_index = 0` using the locked format with current resolved mentions
3. Do NOT re-vectorize body chunks — they remain intact
4. Set `user_note_indexed_at = NULL` → background job picks up note and re-runs targeted entity integration

---

## Notes are searchable

### Full-text search

Add `user_note` to the `full_text_tsv` expression in the document insert trigger or update:

```sql
UPDATE documents
SET full_text_tsv = to_tsvector('english',
    COALESCE(original_filename, '') || ' ' ||
    COALESCE(summary, '') || ' ' ||
    COALESCE(user_note, '')         -- NEW
)
WHERE id = :doc_id;
```

The TSV must be refreshed whenever `user_note` changes (in the PATCH endpoint, after the update statement, or via a trigger). Don't forget this when implementing the PATCH endpoint.

### Note facet in search

The existing search resolver (`api/app/services/search/resolver.py`) scores documents by full-text match and semantic similarity. Since `user_note` is now in `full_text_tsv`, it participates automatically.

Add a dedicated `note_match` score boost: if the query text appears in `user_note` via `to_tsquery`, add `+0.3` to the document's relevance score. This makes note-heavy queries surface correctly even when the raw document text doesn't match.

---

## Notes appear in chat retrieval

### Path 1 — Semantic (automatic once vectorized)

Note chunks are in the `chunks` table after vectorization. The semantic search path in chat retrieval (`kg_retriever` calls vector similarity search) will return them like any other chunk. The note chunk's embedded text (note + entity names + filename) gives it strong semantic recall for entity-name queries. No code changes needed in `kg_retriever.py` or `fusion.py` for this path.

### Path 2 — Entity mention path

In `kg_retriever.py`, when resolving entity X and retrieving facts, also query `note_entity_mentions` for documents that explicitly mention entity X in a note:

```python
# After fact retrieval, also find documents with note mentions of this entity
mention_docs = await db.execute(
    text("""
        SELECT d.id, d.original_filename, nem.mention_text
        FROM note_entity_mentions nem
        JOIN documents d ON d.id = nem.document_id
        JOIN entities e ON e.id = nem.entity_id
        WHERE nem.entity_id = :eid AND nem.user_id = :uid
          AND e.deleted_at IS NULL                       -- filter merged entities
    """),
    {"eid": str(entity_id), "uid": str(user_id)},
)
```

This ensures: "What documents mention my mother?" retrieves docs even if the semantic embedding didn't surface them. The `deleted_at IS NULL` filter is mandatory (see audit task ND-D-05).

---

## API surface

### POST /api/documents (existing, unchanged schema)
The `user_note` field is already accepted in `DocumentCreateSchema`. The dropzone just needs to send it.

### PATCH /api/documents/:id/note (new endpoint)

```typescript
// web/app/api/documents/[id]/note/route.ts
const NoteUpdateSchema = z.object({
  user_note: z.string().max(2000),  // 2000 char limit
});
```

- Validates auth (user must own the document)
- Updates `documents.user_note` and resets `user_note_indexed_at = NULL`
- Updates `full_text_tsv` (manually or via trigger)
- Enqueues a background note re-integration job (not the full pipeline)
- Returns `{ ok: true }`

Backend API counterpart:
```
POST /note-reintegrate  { doc_id: UUID }
```
This endpoint runs only: load note → parse mentions → resolve via `entity_resolver.resolve_and_persist()` (single-mention shape) → update `note_entity_mentions` → re-emit chunk_index=0 → set `user_note_indexed_at = now()`. Skips text extraction, classification, field extraction, verification.

### GET /api/documents/:id (existing)
Ensure `user_note` is included in the response. Currently, `loadDocument` in the detail page does `select("*")` — the column is returned but ignored. Add `user_note` to the `DocumentDetail` interface.

---

## UX

### Upload — notes textarea

In `dropzone.tsx`, after the drop zone and before the file list, add:

```
┌─────────────────────────────────────────────────┐
│ Add a note (optional)                           │
│ ┌─────────────────────────────────────────────┐ │
│ │ e.g. "This is my mother's passport"         │ │
│ │ Use @Name to link to people, #tag to tag    │ │
│ └─────────────────────────────────────────────┘ │
│ The note helps the system understand context     │
└─────────────────────────────────────────────────┘
```

- Single shared textarea for all files dropped in one batch (simplest UX; can be per-file in a later phase)
- Sent as `user_note` in the POST payload along with the file metadata
- 2000 character limit with counter
- The dropzone does NOT need autocomplete (entity-creation-from-mention is allowed via document-detail editing where autocomplete is provided); upload-time mentions remain unresolved until the user opens the document detail and confirms them, OR until they re-edit the note from detail

### Document detail — editable notes panel

Add a panel between the summary card and the extracted fields section:

```
┌─────────────────────────────────────────────────┐
│ Your note                              [Edit]   │
├─────────────────────────────────────────────────┤
│ This is my mother's passport. [Sunita Sharma]   │
│ #travel #family                                  │
└─────────────────────────────────────────────────┘
```

Rendering rules:
- Resolved `@mention` → rendered as a chip/pill with the entity's canonical name (e.g., `[Sunita Sharma]`), styled accent color
- Unresolved `@text` → rendered as plain text in a muted color (e.g., grey `@text`), no chip
- `#tag` → rendered as a small tag chip

Editing:
- Clicking Edit replaces the read view with a `<textarea>` + Save/Cancel
- `@` character opens an entity autocomplete dropdown:
  - Fuzzy-searches `entities.canonical_name` and `entities.aliases` in real time
  - Shows up to 5 existing-entity suggestions
  - Shows a "Create new entity: <typed>" option ONLY when at least 2 characters have been typed after the `@`
  - User MUST pick a suggestion to resolve the mention; leaving the dropdown without picking → mention stays unresolved
  - Debounce: 200ms client-side (see KNOWLEDGE.md gotcha #7)
- `#` character opens a tag autocomplete: lists existing tags from `documents.metadata.tags` across all user documents
- On Save: calls PATCH /api/documents/:id/note → shows a "Re-processing note…" spinner → on completion shows "Note saved"
- Autocomplete is implemented purely client-side using Supabase `.from("entities").select("id, canonical_name").is("deleted_at", null).ilike("canonical_name", "%{query}%")` — no new API endpoint needed. Note the `deleted_at` filter — merged entities must not appear in autocomplete.

### Edit-after-upload semantics — important

When a user edits a note after the document has already been processed:
1. **Entity integration re-runs targeted** (lightweight — only the note path, not the full pipeline)
2. **Note chunk (chunk_index=0) re-vectorizes** (only the note chunk, body chunks unchanged)
3. **Existing entities and facts are NOT deleted** — the re-integration adds new relationships/mentions but does not roll back previous ones. If a note contradiction exists, the LLM emits a new resolution and the entity_resolver handles it additionally.
4. **`user_note_indexed_at`** is reset to NULL on save, set to `now()` after background processing completes

This must be documented clearly in the UI: "Saving a note will update the knowledge graph. Existing connections from this document are not removed."

---

## Implementation checklist summary

- [ ] DB migration: add `user_note_indexed_at` column; create `note_entity_mentions` table
- [ ] `KnowledgeIntegratorInput`: add `user_note` field
- [ ] KI prompt: add note context section
- [ ] `_integrate` in orchestrator: load `user_note` and pass through
- [ ] `vectorize_document`: load and include `user_note` + resolved mention names in chunk_index=0 composition; body chunks start at chunk_index=1
- [ ] New endpoint `PATCH /api/documents/:id/note` (web BFF) — also refreshes full_text_tsv
- [ ] New endpoint `POST /note-reintegrate` (FastAPI backend) — uses `entity_resolver.resolve_and_persist()` for mention entity creation
- [ ] `@mention` parser: extract `@Name` tokens with char offsets
- [ ] Mention resolver: takes confirmed picks from frontend; writes `note_entity_mentions` rows; bypassing `entity_resolver` for "new entity from mention" is FORBIDDEN
- [ ] `#tag` parser: extract `#tag` tokens, write to `documents.metadata.tags`
- [ ] Dropzone: add notes textarea
- [ ] Document detail: add editable notes panel with resolved/unresolved rendering + autocomplete (filtered to `deleted_at IS NULL`)
- [ ] `kg_retriever.py`: add note mention path to entity retrieval (with `deleted_at IS NULL` filter)
- [ ] Full-text TSV: include `user_note`; refresh in PATCH
- [ ] Tests for all of the above
- [ ] Tracing: `note_reintegration` and `mention_resolution` Langfuse spans (see ND-H-04)
