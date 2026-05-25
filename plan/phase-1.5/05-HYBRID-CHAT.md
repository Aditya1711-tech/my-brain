# 05 — Hybrid Chat (KG + Vector Fusion)

The single most important user-facing change in Phase 1.5. Today's cross-doc chat is vector-only with a weak keyword-match KG patch. After 1.5, the system **uses both KG and vector retrieval together**, intelligently combining them for every answer.

## Design principles

1. **Both sources always, never "fallback"** — KG and vector retrieval run **in parallel** for every cross-doc question. The fusion step decides how to weight them.
2. **KG is authoritative for facts; vectors are authoritative for context.** A fact ("Priya's passport expires 2034-08-15") comes from KG. The surrounding context ("...issued by the Regional Passport Office, Mumbai, mentioned that she's a Class-A passport holder") comes from chunks.
3. **Citations cover both.** Every claim in the answer is traceable to either a KG fact (with source_document_id) or a chunk (with chunk_id).
4. **Conversation history is preserved** so users can follow up naturally.
5. **Question routing is a hint, not a gate.** The router classifies questions but both retrievers always run — the router just adjusts weights.

---

## Architecture

```
Question + History
       ↓
┌───────────────────────┐
│ Question router       │  → routing_hint: factual | semantic | mixed
│ (Haiku, fast)         │     + entity_hints: [Priya, Rahul, ...]
└──────────┬────────────┘     + intent: lookup | summarize | compare | ...
           │
           ├────────────────────┬────────────────────┐
           ▼                    ▼                    ▼
   ┌──────────────┐    ┌──────────────────┐  ┌──────────────────┐
   │ KG retriever │    │ Vector retriever │  │ Entity resolver  │
   │ (deterministic+│   │ (pgvector cosine)│  │ (relation terms) │
   │  graph walk)  │    │ within user docs │  │ "wife" → entity  │
   └──────┬───────┘    └────────┬─────────┘  └────────┬─────────┘
          │                     │                     │
          └──────────┬──────────┴─────────────────────┘
                     ▼
          ┌────────────────────────┐
          │ Fusion + reranker      │
          │ - merge KG facts +     │
          │   chunks               │
          │ - rerank by intent     │
          │ - dedupe by entity     │
          └──────────┬─────────────┘
                     ▼
          ┌────────────────────────┐
          │ Responder              │
          │ - structured context   │
          │ - conversation history │
          │ - inline citations     │
          │ (Sonnet, streaming)    │
          └──────────┬─────────────┘
                     ▼
              SSE stream out
```

---

## Question router

Lightweight Haiku call that produces a structured hint:

```python
class RoutingHint(BaseModel):
    intent: Literal["lookup", "summarize", "compare", "list", "explain", "follow_up"]
    routing: Literal["factual", "semantic", "mixed"]
    entity_terms: list[str]      # raw terms from question that may name entities or relations
    field_terms: list[str]       # raw terms that may name fields (e.g., "expiry date", "passport number")
    time_terms: list[str]        # date references in the question
    refers_to_prior: bool        # true if "the", "it", "that one" etc. — needs history resolution
```

Examples:

| Question | Intent | Routing | Entity terms | Field terms |
|----------|--------|---------|--------------|-------------|
| "When does Priya's passport expire?" | lookup | factual | [Priya, passport] | [expiry, expire] |
| "What was the doctor's recommendation in my last report?" | lookup | semantic | [doctor, report] | [recommendation] |
| "Compare my and my wife's passport expiry dates" | compare | mixed | [wife, passport] | [expiry] |
| "Summarize the marriage cert" | summarize | semantic | [marriage cert] | [] |
| "And the expiry date?" | follow_up | mixed | [] | [expiry] |

Implementation: Haiku call with a small system prompt + recent message history. Fast and cheap.

---

## Entity resolver

Resolves natural-language references to specific entity IDs:

```python
class ResolvedEntity(BaseModel):
    entity_id: UUID
    canonical_name: str
    resolution_path: str   # "alias" | "relation_term" | "fuzzy" | "graph_walk"
```

Resolution order:
1. **Exact / alias match** on `entities.canonical_name` and `entities.aliases`
2. **Relation term** (wife/husband/son/etc.) → resolve via current user's "self" entity + entity_relationships traversal
3. **Fuzzy** (trigram > 0.5) on canonical_name and aliases
4. **From conversation history** — if the question says "the", "that one", scan recent assistant turns for entity references

The "self" entity is the entity created from the user's own documents (passport, driving license, etc., where they are the subject role). Detected as: the entity with the most `role='subject'` document_entities of personal-domain documents. Cached.

---

## KG retriever

`services/chat/kg_retriever.py`. Produces structured `KGFact` rows:

```python
class KGFact(BaseModel):
    entity_id: UUID
    entity_name: str
    field_name: str
    field_value: str
    field_type: str
    confidence: float
    source_document_id: UUID
    source_document_name: str
    valid_from: datetime
    valid_until: datetime | None  # null = current
```

Query plan based on routing hint:

```python
async def retrieve(self, user_id, hint, resolved_entities, history):
    facts = []

    # 1. If specific entities resolved → get their current facts matching field terms
    if resolved_entities:
        for ent in resolved_entities:
            entity_facts = await self._facts_for_entity(
                user_id, ent.entity_id, field_terms=hint.field_terms
            )
            facts.extend(entity_facts)

    # 2. If question has relation terms → traverse one hop
    if any_relation_term(hint.entity_terms):
        for ent in resolved_entities:
            related = await self._related_entities(user_id, ent.entity_id)
            for rel_entity in related:
                rel_facts = await self._facts_for_entity(user_id, rel_entity.id, field_terms=hint.field_terms)
                facts.extend(rel_facts)

    # 3. If no specific entity but specific field term ("show me all passports") → field-name search
    if not resolved_entities and hint.field_terms:
        field_facts = await self._facts_by_field_names(user_id, hint.field_terms)
        facts.extend(field_facts)

    # 4. Time filter
    if hint.time_terms:
        facts = filter_by_time(facts, hint.time_terms)

    # Dedupe by (entity_id, field_name) keeping current (valid_until IS NULL) and most-recent
    return dedupe_facts(facts)
```

**Critical:** the KG retriever queries:
- `facts` joined with `entities` and `documents` (gets value + entity name + source doc) ✓
- `entity_relationships` for relation traversal ✓
- `document_entities` to surface "which docs mention this entity" ✓

All three were missing in Phase 1.

---

## Vector retriever

Mostly the existing `retrieve_cross_document_chunks`, with two changes:

1. **Hybrid retrieval** — combine vector cosine similarity with BM25 (PostgreSQL `ts_rank`) using reciprocal rank fusion. The cross-doc retrieve today is vector-only; single-doc retrieve is also vector-only. Add BM25 to both.
2. **Entity-biased retrieval** — if entities resolved, boost chunks from documents linked to those entities (via `document_entities`).

```python
async def retrieve(self, user_id, query, resolved_entity_ids: list[UUID] | None, top_k=12):
    q_embedding = (await get_embeddings([query]))[0]
    embedding_str = format_vector(q_embedding)

    boost_clause = ""
    if resolved_entity_ids:
        # Soft boost: chunks from docs linked to these entities get a similarity bump
        boost_clause = """
            + CASE WHEN c.document_id IN (
                SELECT document_id FROM document_entities WHERE entity_id = ANY(:entity_ids)
              ) THEN 0.1 ELSE 0.0 END
        """

    # Vector + BM25 + boost
    result = await db.execute(text(f"""
        SELECT c.id, c.chunk_index, c.text, c.document_id, d.original_filename,
               (
                 (1 - (c.embedding <=> CAST(:embedding AS vector)))
                 + COALESCE(ts_rank(d.full_text_tsv, plainto_tsquery('english', :query)), 0) * 0.5
                 {boost_clause}
               ) AS combined_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.user_id = :uid AND d.deleted_at IS NULL
        ORDER BY combined_score DESC
        LIMIT :top_k
    """), {...})
```

The 0.5 BM25 weight and 0.1 entity-boost are starting values — tunable.

---

## Fusion + reranker

`services/chat/fusion.py`. Takes KG facts and chunks, produces a single ordered context list:

```python
class ContextItem(BaseModel):
    type: Literal["kg_fact", "chunk"]
    content: str                  # rendered for the LLM
    citation: Citation
    weight: float                 # 0.0 - 1.0, influences ordering

def fuse(kg_facts: list[KGFact], chunks: list[Chunk], hint: RoutingHint) -> list[ContextItem]:
    items = []

    # Render KG facts
    for fact in kg_facts:
        items.append(ContextItem(
            type="kg_fact",
            content=f"{fact.entity_name} — {fact.field_name}: {fact.field_value} (source: {fact.source_document_name})",
            citation=Citation(type="kg_fact", entity_id=fact.entity_id, field_name=fact.field_name,
                              source_document_id=fact.source_document_id),
            weight=1.0 if hint.routing in ("factual", "mixed") else 0.6,
        ))

    # Render chunks
    for c in chunks:
        items.append(ContextItem(
            type="chunk",
            content=f"[from {c.filename}]: {c.text}",
            citation=Citation(type="chunk", chunk_id=c.id, document_id=c.document_id),
            weight=1.0 if hint.routing in ("semantic", "mixed") else 0.5,
        ))

    # Dedupe — if a chunk text already contains the value of a fact, drop the chunk's redundancy
    items = dedupe_overlapping(items)

    # Sort by weight, then by intrinsic score
    items.sort(key=lambda x: x.weight, reverse=True)

    # Cap context budget — keep top items that fit in ~3000 tokens
    items = budget_clip(items, max_tokens=3000)

    return items
```

---

## Responder with history

`services/chat/responder.py` reshaped:

```python
async def stream_response(
    *,
    user_id: UUID,
    thread_id: UUID,
    message: str,
    context_items: list[ContextItem],
    history: list[ChatMessage],
) -> AsyncGenerator[str, None]:

    # 1. Emit citations upfront so frontend can render references
    for ci in context_items:
        yield sse("citation", ci.citation.model_dump())

    # 2. Build the Claude messages array with conversation history
    system_prompt = build_system_prompt(has_kg=any(c.type == "kg_fact" for c in context_items))
    context_block = render_context(context_items)
    messages = []
    # Replay history (alternating user/assistant)
    for h in history[-12:]:  # last ~6 exchanges
        messages.append({"role": h.role, "content": h.content})
    # Append current turn with context
    messages.append({"role": "user", "content": f"{context_block}\n\n---\n\nQuestion: {message}"})

    # 3. Stream
    async with anthropic_client.messages.stream(
        model=MODEL_CHAT,
        max_tokens=2048,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for token in stream.text_stream:
            yield sse("text_delta", {"text": token})

    yield sse("done", {})
```

System prompt:

```
You are answering questions about the user's documents.

You have two kinds of context:
1. KNOWLEDGE GRAPH FACTS: structured, authoritative records extracted from documents. Treat these as truth.
2. DOCUMENT CHUNKS: relevant excerpts for context, surrounding detail, and nuance.

Rules:
- If KG facts directly answer the question, lead with them and cite the source document.
- Use chunks for elaboration, surrounding context, and questions that aren't simple facts.
- Cite every claim. Use [F1], [F2] for facts and [C1], [C2] for chunks. Citation IDs match the order of context items provided.
- Never invent facts. If neither source supports an answer, say "I don't have that in your documents."
- Be concise. Aim for 1-3 sentences unless the user asked for more detail.
- For follow-up questions, treat pronouns ("the", "that", "she") as referring to entities or documents mentioned in earlier turns.
```

---

## Single-document chat

The single-document path stays mostly as it is, with two additions:
1. Use thread history (chat memory)
2. Add BM25 alongside vector retrieval within the document (hybrid in-doc)

KG retrieval isn't useful for single-doc scope (the KG is shared across all docs; querying it for facts about "this document" would surface other documents' facts about the same entity, which is confusing in single-doc context). Skip KG for single-doc.

---

## Schema changes

```sql
-- chat threads
CREATE TABLE chat_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  scope TEXT NOT NULL,        -- 'all' | 'document'
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,  -- null when scope='all'
  title TEXT,                  -- auto-generated from first message
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON chat_threads(user_id, updated_at DESC);

-- chat messages
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  role TEXT NOT NULL,          -- 'user' | 'assistant'
  content TEXT NOT NULL,
  citations JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON chat_messages(thread_id, created_at);

-- RLS
ALTER TABLE chat_threads ENABLE ROW LEVEL SECURITY;
CREATE POLICY chat_threads_select_own ON chat_threads FOR SELECT USING (user_id = auth.uid());
-- ... same pattern for insert/update/delete
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
-- ... policies via thread ownership
```

---

## API surface changes

```
POST /chat
  Auth: JWT (D-AUTH-01 fix)
  Body: {
    "thread_id": "uuid | null",   // null = create new thread
    "scope": "all" | "document",
    "document_id": "uuid | null",
    "message": "string"
  }
  Response: SSE stream with events:
    - thread { id }
    - citation { type, ... }
    - text_delta { text }
    - done { usage }

GET /threads — list user's threads
GET /threads/:id/messages — load thread history
DELETE /threads/:id — delete thread
```

Frontend changes:
- Chat page has a left list of threads, main area shows current thread
- Single-doc chat creates an auto-thread per document; reopening the doc resumes that thread
- Citation badges render with different icons for KG facts vs chunks

---

## Latency budget

Target: cross-doc chat first token ≤ 2.5 s p50.

Breakdown:
- Question router (Haiku, ~300 input tokens, ~150 output) ≈ 400 ms
- KG retriever (3-4 DB queries) ≈ 80 ms
- Vector retriever (embedding + hybrid query) ≈ 250 ms
- Fusion + dedupe (sync) ≈ 20 ms
- Responder first token (Sonnet streaming starts) ≈ 1500 ms

Total: ~2250 ms. Tight but achievable.

Parallelize the three retrievers (router result feeds both KG and vector — fire them concurrently):

```python
async def cross_doc_chat(user_id, thread_id, message):
    history = await get_history(thread_id)
    hint = await router.classify(message, history)
    resolved = await resolve_entities(user_id, hint, history)

    kg_task = asyncio.create_task(kg_retriever.retrieve(user_id, hint, resolved, history))
    vec_task = asyncio.create_task(vector_retriever.retrieve(user_id, message, [r.entity_id for r in resolved]))
    kg_facts, chunks = await asyncio.gather(kg_task, vec_task)

    items = fuse(kg_facts, chunks, hint)
    async for evt in responder.stream(...):
        yield evt
```

---

## What single-doc chat keeps

- Stays vector + (new) BM25 within document
- Adds thread history
- Does NOT do KG retrieval (would surface other documents' facts, confusing)

---

## Eval / smoke tests for chat

A small chat eval suite (in `tests/integration/test_chat_quality.py`) that:
- Seeds a test user with 5 fixture documents (passport for self, passport for spouse, marriage cert, x-ray report, invoice)
- Runs 10 scripted Q&A pairs covering: factual lookup, follow-up, relationship traversal, semantic (chunk-based), no-answer ("when's my mom's birthday?" with no mom doc)
- Asserts citations are emitted with correct types
- Asserts answers contain expected facts (or correctly say "I don't have that")
- Cost-cap: total eval run ≤ $0.50

This isn't a perfection test — LLM answers vary — but it catches regressions.
