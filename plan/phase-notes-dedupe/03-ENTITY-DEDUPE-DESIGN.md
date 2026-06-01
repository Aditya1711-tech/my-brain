# 03 — Entity Deduplication Design

## Why duplicates happen today

From discovery (`00-DISCOVERY.md`):

1. **Trigram threshold too permissive (0.3):** Candidates are retrieved broadly, but the LLM needs to decide. With only `canonical_name, aliases, identifiers` as context, a name like "Aditya Kumar" vs "A. Kumar Sharma" has no identifier match and no DOB → LLM marks `uncertain`.

2. **`uncertain` silently creates a new entity AND throws away the signal:** `entity_resolver.py` line 102 treats `uncertain` identically to `create_new`. There is no review queue, no merge suggestion, no flag, and crucially — the fact that the LLM was uncertain *about a specific set of candidates* is lost. The dedupe sweep then has to re-discover the duplication from scratch using only name similarity.

3. **KI prompt rule 3 is dead code:** The prompt says "Strong name similarity + shared family relationships → match" but the candidate context sent to the LLM contains NO relationship data. The LLM cannot apply rule 3 as written.

4. **No phonetic matching:** "Advika" and "Adwika" have trigram similarity ~0.5 — below the threshold for confident match but above random noise. Soundex/Metaphone would collapse them to the same code.

5. **No DOB or linked-doc-type signals in candidate matching:** If two candidates have the same name but one has DOB "1985-03-12" in facts, a new document mentioning the same DOB should hard-match — but `find_candidates` doesn't look at `facts` at all.

---

## Prevention layer

### A. Improve `find_candidates`

**1. Raise trigram threshold for pre-filtering from 0.3 to 0.5**

Fewer false candidates → less noise for the LLM → fewer `uncertain` decisions. The current threshold 0.3 over-retrieves; 0.5 still catches common variants ("Sunita" / "Sunita Sharma") while excluding random noise.

**2. Add phonetic matching (Metaphone via Python)**

Use the `metaphone` library (or `jellyfish.metaphone`). Compute metaphone codes for detected names. Pre-compute and store `entities.name_metaphone text` (new column) on insert/update. Add to `find_candidates`:

```python
# Phonetic match (Metaphone)
for i, name in enumerate(names):
    code = compute_metaphone(name)
    if code:
        param_key = f"meta_{i}"
        conditions.append(f"name_metaphone = :{param_key}")
        params[param_key] = code
```

This catches: Advika/Adwika, Singh/Sinha, Sharma/Sarma, etc.

**3. Add DOB cross-reference from `facts` table**

If the detected entity has a `dob` field, add a subquery:

```python
if dob_value:
    conditions.append("""
        id IN (
            SELECT entity_id FROM facts
            WHERE field_name = 'dob' AND field_value = :dob_val
              AND user_id = :user_id AND valid_until IS NULL
        )
    """)
    params["dob_val"] = dob_value
```

A DOB match is as definitive as a passport match for persons.

**4. Add linked document-type context**

`find_candidates` returns additional context column `linked_doc_types text[]`:

```sql
SELECT e.id, e.entity_type, e.canonical_name, e.aliases, e.identifiers, e.name_metaphone,
       ARRAY_AGG(DISTINCT d.doc_type) FILTER (WHERE d.doc_type IS NOT NULL) AS linked_doc_types
FROM entities e
LEFT JOIN document_entities de ON de.entity_id = e.id
LEFT JOIN documents d ON d.id = de.document_id
WHERE e.user_id = :user_id
  AND e.deleted_at IS NULL                    -- exclude merged entities
  AND (<other conditions>)
GROUP BY e.id, ...
```

This gets passed to the KI: "This entity is already linked to [passport, aadhaar, birth_cert]" — if the new document is the same type as one already linked, it's a strong signal for match. The `deleted_at IS NULL` clause is mandatory (see audit task ND-D-05).

### B. Richer candidate context for the KI

Serialize to `existing_entities` for KI (expanded):

```python
existing_entities.append({
    "id": str(c["id"]),
    "entity_type": c["entity_type"],
    "canonical_name": c["canonical_name"],
    "aliases": c["aliases"] if isinstance(c["aliases"], list) else [],
    "identifiers": c["identifiers"] if isinstance(c["identifiers"], dict) else {},
    # NEW:
    "relationships": relationships_for(c["id"]),   # e.g. ["spouse_of:Aditya", "child_of:Ramesh"]
    "linked_doc_types": c["linked_doc_types"] or [],
    "known_dob": known_dob_for(c["id"]),           # from facts if available
})
```

Load relationships in a batch query before the KI call (one query for all candidate IDs, not N queries). Keep to max 5 relationship entries per candidate to avoid prompt bloat.

### C. Fix the `uncertain` path — preserve KI's signal

When the KI returns `uncertain`, we now do two things:

1. **Create the new entity** (so the pipeline doesn't block). This preserves the existing non-blocking behavior — the document can still complete processing.
2. **Immediately write `entity_duplicate_candidates` rows pairing the new entity against each candidate the KI considered.** Each row gets `confidence = 0.5`, `reason = "ki_uncertain"`, and `status = 'pending'`. The detection sweep then sees these as candidates needing review on its first run — no waiting, no signal loss.

```python
# in entity_resolver.py, uncertain branch
if decision == "uncertain":
    new_entity_id = await self.entities_repo.create(
        user_id=user_id, entity_type=type, canonical_name=name, ...
    )
    # Write candidate rows pairing new entity against each KI-considered candidate
    for candidate_id in considered_candidate_ids:
        await self.duplicate_candidates_repo.upsert(
            user_id=user_id,
            entity_id_a=min(new_entity_id, candidate_id),
            entity_id_b=max(new_entity_id, candidate_id),
            confidence=0.5,
            reason="ki_uncertain",
            ki_reasoning=ki_decision.reasoning,
        )
    logger.info("ki_uncertain_signal_preserved",
                new_entity=str(new_entity_id),
                considered_count=len(considered_candidate_ids))
```

This eliminates the need for a separate `entity_resolution_queue` table — `entity_duplicate_candidates` does the job, and it integrates naturally with the detection sweep and the merge UI.

### D. Notes help prevention (synergy with Track A)

When a note says "@Mom — this is her passport", the KI receives:
- Detected entity: "Sunita Devi" (extracted from passport)
- User note: "@Mom — this is her passport"
- Existing entities: "Sunita Devi" (canonical, 3 docs) as candidate

The LLM can now confidently choose `match_existing` even if trigram similarity is borderline. The note provides the missing disambiguation signal.

---

## Detection layer

### New table: `entity_duplicate_candidates`

```sql
CREATE TABLE entity_duplicate_candidates (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entity_id_a     uuid NOT NULL REFERENCES entities(id),
    entity_id_b     uuid NOT NULL REFERENCES entities(id),
    confidence      float NOT NULL,                       -- 0.0–1.0
    reason          text NOT NULL,                        -- e.g. "name_similarity=0.85,shared_doc", "ki_uncertain", "phonetic_match"
    ki_reasoning    text,                                 -- captured when reason='ki_uncertain'
    status          text NOT NULL DEFAULT 'pending',      -- pending | merged | dismissed
    auto_merge_eligible boolean DEFAULT false,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    reviewed_at     timestamptz,
    UNIQUE (user_id, entity_id_a, entity_id_b),
    CHECK (entity_id_a < entity_id_b)                     -- canonical ordering prevents duplicates
);
CREATE INDEX idx_edc_user_status ON entity_duplicate_candidates(user_id, status);
```

### Detection sweep algorithm

Callable as `python -m app.scripts.dedupe_sweep [--user-id UUID] [--dry-run]`

```
For each user (or specified user), considering only entities WHERE deleted_at IS NULL:

  1. Name similarity pass:
     SELECT pairs (a, b) WHERE
       similarity(a.canonical_name, b.canonical_name) > 0.7
       AND a.entity_type = b.entity_type
       AND NOT EXISTS (contradicting_identifier)
     → base confidence = similarity score

  2. Shared identifier pass:
     SELECT pairs (a, b) WHERE
       a.identifiers @> b.identifiers  -- any overlapping key-value
       AND a.id != b.id
     → confidence = 1.0 (this should not be possible given Phase 1.5, but verify)

  3. Shared document pass:
     SELECT pairs (a, b) WHERE
       EXISTS (same document linked to both)
       AND similarity(a.canonical_name, b.canonical_name) > 0.5
     → confidence += 0.15

  4. Phonetic match pass:
     SELECT pairs (a, b) WHERE
       a.name_metaphone = b.name_metaphone
       AND a.name_metaphone IS NOT NULL
     → confidence = max(existing, 0.75)

  5. For each identified pair, UPSERT into entity_duplicate_candidates:
     - Pre-existing pairs with status 'merged' or 'dismissed' → skipped entirely
     - Pre-existing pairs with status 'pending' → confidence = MAX(existing.confidence, new.confidence)
       (Monotonic — confidence only goes up across re-scans. A pair that scored 0.8 on first run and
        0.7 on second run keeps 0.8. This prevents a regression where a previously-flagged duplicate
        becomes invisible because the second pass scored it lower.)
     - New pairs → insert with computed confidence
     - In all UPSERT cases: if confidence > 0.95 → auto_merge_eligible = true

  6. Pairs from the `ki_uncertain` path:
     - Already written by entity_resolver during pipeline runs (see "Fix the uncertain path" above)
     - The sweep also evaluates them with the algorithmic checks above; if the algorithmic confidence
       is higher than the original 0.5, the row is updated to the higher value (MAX rule)

  7. Report: N pairs found, X auto-merge eligible, Y for review
```

Idempotency:
- Pairs in `entity_duplicate_candidates` with status `merged` or `dismissed` are skipped.
- Pairs in status `pending` are UPSERTed using `MAX(existing, new)` for confidence — re-runs never reduce confidence.
- Re-running adds only genuinely new pairs.

---

## Merge layer

### Merge semantics

Given entity A (winner) and entity B (loser):

1. **Transfer document_entities:** `UPDATE document_entities SET entity_id = A WHERE entity_id = B AND entity_id != A` (ON CONFLICT DO NOTHING)
2. **Transfer entity_relationships:** For each relationship of B, check if A already has an equivalent (same type, same partner). If not, create it. If yes, skip.
3. **Transfer aliases:** Merge B's `aliases` and `canonical_name` into A's aliases array (dedup)
4. **Transfer identifiers:** `UPDATE entities SET identifiers = identifiers || B.identifiers WHERE id = A` (B's identifiers added to A; B's win on key collision is acceptable since identifiers are typed and rarely conflict)
5. **Transfer `note_entity_mentions`:** `UPDATE note_entity_mentions SET entity_id = A WHERE entity_id = B`
6. **Transfer facts** — see "Fact conflict resolution during merge" below
7. **Soft-delete B:** `UPDATE entities SET deleted_at = now() WHERE id = B`
8. **Update `entity_duplicate_candidates`:** Set `status = 'merged', reviewed_at = now()` for all rows involving B
9. **All in a single transaction**

### Fact conflict resolution during merge

For each fact on B, determine the action by comparing against A's current fact with the same `field_name`:

| State on A | State on B | Action |
|---|---|---|
| Has current value | No fact | (nothing to transfer) |
| No current value | Has current value | **Inherit B's value as A's current fact.** Insert a new fact row on A with B's `field_value`, `field_type`, `confidence`, and `source_document_id`. Set `valid_from = B.valid_from`, `valid_until = NULL`. This is "fill blanks from loser." |
| Has current value | Has current value | Keep A's current fact unchanged. Archive B's value: insert a row on A with B's `field_value`, `field_type`, `confidence`, `source_document_id`, `valid_from = B.valid_from`, and `valid_until = now()` so it appears as a historical (superseded) fact. |
| Has historical (superseded) value | Has any value | (rare case) Apply same rules as above using A's most recent current fact for comparison. |

Why this matters: a merge where "winner wins on conflict" without inheriting blanks loses information when the loser had better partial data than the winner. Example: A is "Sunita Sharma" with `dob = unknown`, B is "Sunita S." with `dob = 1962-08-14`. Standard "winner wins" would drop the DOB. The "fill blanks from loser" rule above preserves it.

Implementation note: this requires reading A's current facts first (one query) and then deciding per fact. Wrap in the same transaction as the other merge steps.

### Merge API

```
POST /api/entities/merge
Body: { winner_id: UUID, loser_id: UUID }
Auth: user must own both entities
Returns: { ok: true, winner_id: UUID, summary: { facts_inherited, facts_archived, docs_transferred, relationships_added } }
```

Backend endpoint in FastAPI:
```python
@router.post("/entities/merge")
async def merge_entities(body: MergeRequest, user_id: UUID = Depends(get_current_user)):
    summary = await EntityMergeService(db).merge(
        user_id=user_id,
        winner_id=body.winner_id,
        loser_id=body.loser_id,
    )
    return {"ok": True, "winner_id": str(body.winner_id), "summary": summary}
```

Returning a summary helps the UI show a confirmation toast (e.g., "Merged 2 facts inherited, 1 archived, 3 docs transferred").

### Merge UI (minimal)

Location: graph page, in the `EntitySidePanel`

Add a "Merge with…" button. On click:
- Opens a simple modal: "Merge [Entity A] into another entity"
- Text search box: user types a name, suggests entities via Supabase fuzzy query (with `deleted_at IS NULL` filter)
- User selects target → shows confirmation: "Merge [Loser] into [Winner]? This cannot be undone."
- On confirm: calls `POST /api/entities/merge`
- On success: refreshes graph data (removes loser node, winner gains loser's doc count); shows summary toast

**Auto-merge for high-confidence pairs (Phase F bonus):**

On the dedupe sweep results page (or CLI), offer `--auto-merge` flag that calls the merge API for all pairs with `auto_merge_eligible = true`, respecting the `--max-auto-merges-per-run` cap. CLI is sufficient — no UI required for auto-merge.

---

## Backfill

### Script: `api/app/scripts/dedupe_backfill.py`

```
Usage:
  python -m app.scripts.dedupe_backfill [--user-id UUID] [--dry-run] [--auto-merge-threshold 0.95] [--max-auto-merges-per-run N]

Defaults:
  --auto-merge-threshold = 0.95
  --max-auto-merges-per-run = 10     (safety rail — operator MUST explicitly raise for larger graphs)

Steps:
1. Run the detection sweep for the specified user (or all users)
2. Print a report:
   - Total entities (excluding deleted_at NOT NULL)
   - Total duplicate candidate pairs
   - Pairs by confidence bucket: [0.95–1.0], [0.8–0.95), [0.7–0.8), [0.5–0.7)
3. For pairs with confidence >= --auto-merge-threshold (default 0.95):
   - Order by confidence DESC (highest first)
   - Cap by --max-auto-merges-per-run (default 10)
   - Unless --dry-run: call merge service for each, in order
   - Print: "Auto-merged: X of Y pairs (cap=N)"
   - If Y > N: print "WARNING: Y - N pairs remain auto-mergeable but were not merged because --max-auto-merges-per-run is N. Re-run with a higher cap to continue."
4. For remaining pairs (below threshold or above the cap): print list for manual review

Why the per-run cap:
- A miscalibrated threshold or a quirky fixture could otherwise irreversibly merge dozens of entities on first run
- Combined with --dry-run, gives the operator a safety ladder: dry-run → run with cap=10 → review → re-run with higher cap if needed
- The cap is intentionally low to force human review on first run; raise it explicitly once you've validated the auto-merge behavior on YOUR data

Idempotency guarantee:
- Detection sweep skips pairs already in entity_duplicate_candidates with status 'merged' or 'dismissed'
- Pairs in 'pending' status get UPSERT with MAX(existing, new) confidence — never decreasing
- Merge service is wrapped in a transaction with a check that B is not already deleted
- Safe to re-run: second run reports 0 new auto-merges (because everything ≥ threshold was either merged or rejected for cap), only shows any remaining review items
```

---

## New DB objects summary

```sql
-- entities table additions
ALTER TABLE entities ADD COLUMN name_metaphone text;
ALTER TABLE entities ADD COLUMN deleted_at timestamptz;
CREATE INDEX idx_entities_metaphone ON entities(name_metaphone) WHERE name_metaphone IS NOT NULL;
CREATE INDEX idx_entities_active ON entities(user_id) WHERE deleted_at IS NULL;

-- documents table additions
ALTER TABLE documents ADD COLUMN user_note_indexed_at timestamptz;

-- New tables
CREATE TABLE note_entity_mentions ( ... );   -- see 02-NOTES-DESIGN.md
CREATE TABLE entity_duplicate_candidates ( ... );
```

Note: `entities.deleted_at` does NOT exist per discovery — add in migration.

---

## Audit task: `deleted_at IS NULL` filter (ND-D-05)

Every read query against `entities` (and joins through `entities`) must include `AND deleted_at IS NULL` (or the appropriate variant in JOIN syntax). After Phase F, soft-deleted entities exist and must not surface in:

- Graph view query
- Chat retriever (KG retriever, semantic retriever)
- Entity autocomplete (in note panel and merge UI)
- Search resolver (entity name match)
- Any new endpoint or service

Audit task ND-D-05 enumerates the files touched and ensures every `FROM entities` (including joins) is updated. Commit message must list the files. A regression test seeds two entities, soft-deletes one, and asserts the deleted one does not appear in: graph, chat, autocomplete, search.

---

## Impact on existing code

| File | Change | Reason |
|---|---|---|
| `entities_repo.py` | Expand `find_candidates`: phonetic, DOB, doc-type; add `get_relationships_for_entities` batch query; filter `deleted_at IS NULL` | Prevention layer A+B; audit ND-D-05 |
| `entity_resolver.py` | Pass `user_note` to KI; write `entity_duplicate_candidates` rows on `uncertain` | Prevention layer C+D |
| `knowledge_integrator.py` | Add `user_note` field to `KnowledgeIntegratorInput` | Prevention layer B + Notes |
| KI prompt | Add note section + richer candidate context format | Prevention layer B + Notes |
| `orchestrator.py` | Load `user_note` in `_integrate` | Notes Track A |
| New: `duplicate_candidates_repo.py` | UPSERT with MAX(confidence) logic | Detection layer + uncertain path |
| New: `entity_merge_service.py` | Merge logic in a transaction with fact-conflict resolution | Merge layer |
| New: `dedupe_sweep.py` | Detection algorithm | Detection layer |
| New: `dedupe_backfill.py` | One-time backfill CLI with safety cap | Backfill |
| New: FastAPI endpoint `/entities/merge` | Merge API returning summary | Merge layer |
| `graph-page.tsx` | Add "Merge with…" button in EntitySidePanel (with deleted_at filter on autocomplete) | Merge UI; audit ND-D-05 |
| `kg_retriever.py` | Add `deleted_at IS NULL` filter to all `entities` joins | Audit ND-D-05 |
| `search/resolver.py` | Add `deleted_at IS NULL` filter to entity matching | Audit ND-D-05 |
