# 05 — Parallel Tracks

## Track split

```
Track A — Notes         : Phases A, B, C
Track B — Dedupe        : Phases D, E, F
Sequential at the end   : Phase G (backfill) + Phase H (smoke + tracing audit)
```

Both tracks can be worked independently from session start through Phase C/F. They converge at Phase G (backfill needs merge logic from Track B) and Phase H (smoke requires both).

---

## Track A: Notes (Phases A → B → C)

**Folder ownership:**
- `web/components/upload/dropzone.tsx`
- `web/components/document/document-detail-page.tsx`
- `web/components/document/notes-panel.tsx` (new)
- `web/components/shared/mention-autocomplete.tsx` (new)
- `web/app/api/documents/[id]/note/route.ts` (new)
- `api/app/services/pipeline/vectorizer.py`
- `api/app/services/notes/` (new directory: `mention_parser.py`, `mention_resolver.py`, `tag_parser.py`)
- `api/app/routes/note_reintegrate.py` (new)
- `api/app/services/chat/kg_retriever.py` (the note-mention path addition only)
- `api/app/scripts/backfill_notes.py` (new — ND-G-02)

**Track A does NOT own:**
- `api/app/services/knowledge/entity_resolver.py` — shared (see contract below)
- `api/app/agents/knowledge_integrator.py` — shared
- `api/app/agents/prompts/knowledge_integrator.md` — shared

**Startup task for Track A session:**
1. Read `00-RULES.md`, `PROGRESS.md`, `KNOWLEDGE.md`
2. Read `02-NOTES-DESIGN.md` fully
3. Check `05-PARALLEL-TRACKS.md` for any contract changes from Track B
4. Confirm ND-A-01 has landed on `main` (shared dependency)
5. Confirm Track B's ND-D-03 (KI candidate format change) status — Track A's ND-B-03 depends on it

---

## Track B: Dedupe (Phases D → E → F)

**Folder ownership:**
- `api/app/repositories/entities_repo.py`
- `api/app/repositories/duplicate_candidates_repo.py` (new)
- `api/app/services/knowledge/duplicate_detector.py` (new)
- `api/app/services/knowledge/entity_merge_service.py` (new)
- `api/app/routes/entities.py` (new or extend)
- `api/app/scripts/dedupe_sweep.py` (new)
- `api/app/scripts/dedupe_backfill.py` (new — ND-G-01)
- `api/app/scripts/backfill_metaphone.py` (new — ND-D-01)
- `web/app/api/entities/merge/route.ts` (new)
- `web/components/graph/graph-page.tsx` (merge UI addition only)
- The `uncertain` path in `entity_resolver.py` (only the write-candidate-rows change in ND-D-04)
- Audit task ND-D-05 — touches multiple files across the codebase; commit message lists them

**Track B does NOT own:**
- `api/app/agents/knowledge_integrator.py` — shared
- `api/app/agents/prompts/knowledge_integrator.md` — shared
- Track A's note-handling files (Track A owns those)

**Startup task for Track B session:**
1. Read `00-RULES.md`, `PROGRESS.md`, `KNOWLEDGE.md`
2. Read `03-ENTITY-DEDUPE-DESIGN.md` fully
3. Check `05-PARALLEL-TRACKS.md` for any contract changes from Track A
4. Confirm ND-A-01 has landed on `main`

---

## Shared file contract: KI prompt + input model

Both tracks touch `knowledge_integrator.md` (prompt) and `knowledge_integrator.py` (input model). To prevent merge conflicts:

### Agreed changes (must be implemented in this order)

**Step 1 (Track B does this, in ND-D-03):**
Expand `existing_entities` list format in the prompt to include `relationships`, `linked_doc_types`, `known_dob`. Track B owns this change.

**Step 2 (Track A does this, in ND-B-03):**
Add the `user_note` section to the prompt. Track A owns this change. Append to the prompt — do NOT rewrite the matching rules section or the `existing_entities` format (which Track B owns).

**Integration rule:** When merging tracks, ALWAYS resolve `knowledge_integrator.md` last, manually, by composing both track changes. Never auto-resolve a conflict in this file.

### `KnowledgeIntegratorInput` — agreed fields

Final shape (both tracks must agree before implementation begins):

```python
class KnowledgeIntegratorInput(BaseModel):
    document_type: str
    detected_entities: list[dict]
    extracted_fields: list[dict]
    existing_entities: list[dict]   # Track B adds: relationships, linked_doc_types, known_dob
    user_note: str | None = None    # Track A adds
```

This is the contract. Neither track may add other fields without updating this file and notifying the other track.

### Shared file: `entity_resolver.py`

Track A modifies the function signature (add `user_note` parameter) and pass-through to KI.
Track B modifies the `uncertain` decision branch (write candidate rows).

These edits touch different parts of the same file. Coordinate via PROGRESS.md:
- Track B's ND-D-04 should land first if both are in flight (it's a more contained change at the uncertain branch)
- Track A's ND-B-02 then adds the `user_note` parameter to the function signature and call site

---

## Convergence at Phase G + H

Phase G (backfill) requires:
- `EntityMergeService` from Track B (ND-F-01)
- Detection sweep from Track B (ND-E-02)
- `/note-reintegrate` from Track A (ND-B-04) — for ND-G-02 backfill of existing notes
- Tasks split: ND-G-01 (dedupe backfill) is Track B; ND-G-02 (notes backfill) is Track A

Phase H (smoke + tracing) requires:
- Note BFF from Track A (ND-B-04)
- Mention resolver from Track A (ND-C-02)
- KG retriever note path from Track A (ND-C-04)
- Merge service from Track B (ND-F-01)
- Detection sweep from Track B (ND-E-02)
- Audit complete (ND-D-05)

**Integration session:** Before starting Phase G/H, merge both track branches to `main`, resolve the KI prompt manually, run `pytest -q` and `pnpm typecheck` to confirm no regressions.

---

## PROGRESS.md tracking for parallel tracks

PROGRESS.md has two tracker sections:

```
## Track A task tracker (Notes)
## Track B task tracker (Dedupe)
```

Each session updates only its track's section. The "Current" field at the top of PROGRESS.md shows BOTH tracks' current tasks.

---

## How to start a parallel session

**Session 1 (Track A):**
```
Work on phase-notes-dedupe/track-a/<task-id>
Start with ND-A-01 (migration — both tracks need it, do it first in Track A)
```

**Session 2 (Track B):**
```
Wait for ND-A-01 to merge (migration must exist before Track B can test DB changes)
Work on phase-notes-dedupe/track-b/<task-id>
Track B's first task is ND-D-01 (metaphone column + backfill)
```

ND-A-01 is a shared dependency — it must land on `main` before either track's DB-touching work begins.
