"""Vectorization — chunk text and generate embeddings."""

from uuid import UUID

import structlog
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.langfuse_client import langfuse
from app.integrations.openai_embeddings import get_embeddings

logger = structlog.get_logger()

# ~512 tokens ≈ ~2000 chars; overlap 64 tokens ≈ ~250 chars
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 250
EMBEDDING_BATCH_SIZE = 100


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start >= len(text):
            break
    return chunks


async def vectorize_document(
    db: AsyncSession, doc_id: UUID, user_id: UUID, *, trace_id: str | None = None,
) -> None:
    """Chunk a document's text, compute embeddings, and insert into chunks table."""
    span = None
    if trace_id and langfuse.enabled:
        try:
            trace = langfuse.trace(id=trace_id, name=f"pipeline-{trace_id}")
            span = trace.span(name="vectorization", input={"doc_id": str(doc_id)})
        except (AttributeError, Exception) as exc:
            logger.debug("langfuse_tracing_unavailable", error=str(exc))

    # Load document text + note + metadata
    result = await db.execute(
        sql_text("""
            SELECT raw_text, summary, user_note, original_filename, doc_type
            FROM documents WHERE id = :doc_id
        """),
        {"doc_id": str(doc_id)},
    )
    row = result.fetchone()
    raw_text  = row[0] or "" if row else ""  # type: ignore[index]
    summary   = row[1] or "" if row else ""  # type: ignore[index]
    user_note = row[2] or "" if row else ""  # type: ignore[index]
    filename  = row[3] or "" if row else ""  # type: ignore[index]
    doc_type  = row[4] or "unknown" if row else "unknown"  # type: ignore[index]

    # Load resolved entity names from confirmed @mention picks
    # (written by ND-C-02 mention resolver; empty until that task lands)
    mention_names: list[str] = []
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
        mention_names = [r[0] for r in m_result.fetchall()]  # type: ignore[index]

    # Load extracted field key-value pairs
    fields_result = await db.execute(
        sql_text("""
            SELECT field_name, field_value FROM extracted_fields
            WHERE document_id = :doc_id AND field_value IS NOT NULL
            ORDER BY field_name
        """),
        {"doc_id": str(doc_id)},
    )
    field_pairs = [f"{r[0]}: {r[1]}" for r in fields_result.fetchall()]  # type: ignore[index]

    # ── Note chunk text (chunk_index = 0 — LOCKED FORMAT, do not change) ──────
    # chunk_index = 0 is EXCLUSIVELY reserved for notes. Body chunks start at 1.
    note_chunk_text: str | None = None
    if user_note.strip():
        entity_list = ", ".join(mention_names) if mention_names else "none"
        note_chunk_text = (
            f"Note: {user_note}\n"
            f"Entities mentioned: {entity_list}\n"
            f"Document: {filename} ({doc_type})"
        )

    # ── Body chunks (chunk_index = 1+) ────────────────────────────────────────
    # Note is prepended to body text as well for embedding context continuity.
    parts: list[str] = []
    if user_note.strip():
        parts.append(f"Note: {user_note}")
    if summary:
        parts.append(f"Summary: {summary}")
    if field_pairs:
        parts.append("Extracted fields: " + "; ".join(field_pairs))
    if raw_text:
        parts.append(raw_text)

    body_chunks = chunk_text("\n\n".join(parts)) if parts else []

    if not note_chunk_text and not body_chunks:
        logger.info("vectorizer.skip_empty", doc_id=str(doc_id))
        return

    logger.info(
        "vectorizer.chunking",
        doc_id=str(doc_id),
        note_chunk=note_chunk_text is not None,
        body_chunk_count=len(body_chunks),
    )

    # ── Embed note + body in a single batched pass ────────────────────────────
    all_texts: list[str] = (
        [note_chunk_text] if note_chunk_text else []
    ) + body_chunks

    all_embeddings: list[list[float]] = []
    for i in range(0, len(all_texts), EMBEDDING_BATCH_SIZE):
        batch = all_texts[i : i + EMBEDDING_BATCH_SIZE]
        batch_embeddings = await get_embeddings(batch)
        all_embeddings.extend(batch_embeddings)

    # ── Insert note chunk at index 0 (if present) ─────────────────────────────
    body_start = 0
    if note_chunk_text:
        body_start = 1
        note_emb_str = "[" + ",".join(str(x) for x in all_embeddings[0]) + "]"
        await db.execute(
            sql_text("""
                INSERT INTO chunks (user_id, document_id, chunk_index, text, embedding)
                VALUES (:user_id, :document_id, 0, :text, CAST(:embedding AS vector))
            """),
            {
                "user_id": str(user_id),
                "document_id": str(doc_id),
                "text": note_chunk_text,
                "embedding": note_emb_str,
            },
        )

    # ── Insert body chunks at index 1+ ────────────────────────────────────────
    # Body chunks always start at 1; index 0 is reserved for notes.
    for idx, (chunk_text_val, embedding) in enumerate(
        zip(body_chunks, all_embeddings[body_start:])
    ):
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        await db.execute(
            sql_text("""
                INSERT INTO chunks (user_id, document_id, chunk_index, text, embedding)
                VALUES (:user_id, :document_id, :chunk_index, :text, CAST(:embedding AS vector))
            """),
            {
                "user_id": str(user_id),
                "document_id": str(doc_id),
                "chunk_index": idx + 1,  # 1-based; 0 is reserved for the note chunk
                "text": chunk_text_val,
                "embedding": embedding_str,
            },
        )

    await db.commit()

    chunks_inserted = len(all_texts)
    logger.info(
        "vectorizer.complete",
        doc_id=str(doc_id),
        chunks_inserted=chunks_inserted,
        note_chunk=note_chunk_text is not None,
    )

    if span:
        try:
            span.end(output={
                "chunks_inserted": chunks_inserted,
                "note_chunk": note_chunk_text is not None,
                "body_chunks": len(body_chunks),
            })
        except (AttributeError, Exception):
            pass


async def revectorize_note_chunk(
    db: AsyncSession, doc_id: UUID, user_id: UUID, *, trace_id: str | None = None,
) -> bool:
    """Delete the existing note chunk (index=0) and re-embed from current user_note.

    Called by the /note-reintegrate endpoint after mention rows have been written,
    so mention names are up-to-date when building the chunk text.

    Returns True if a note chunk was emitted, False if user_note is empty/null.
    """
    result = await db.execute(
        sql_text("""
            SELECT user_note, original_filename, doc_type
            FROM documents WHERE id = :doc_id
        """),
        {"doc_id": str(doc_id)},
    )
    row = result.fetchone()
    user_note = row[0] or "" if row else ""
    filename  = row[1] or "" if row else ""
    doc_type  = row[2] or "unknown" if row else "unknown"

    if not user_note.strip():
        logger.info("vectorizer.note_chunk_skip_empty", doc_id=str(doc_id))
        return False

    # Load resolved entity names (written moments ago by MentionResolver)
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

    entity_list = ", ".join(mention_names) if mention_names else "none"
    note_chunk_text = (
        f"Note: {user_note}\n"
        f"Entities mentioned: {entity_list}\n"
        f"Document: {filename} ({doc_type})"
    )

    embeddings = await get_embeddings([note_chunk_text])
    note_emb_str = "[" + ",".join(str(x) for x in embeddings[0]) + "]"

    # Replace existing chunk_index=0 (delete + insert keeps it idempotent)
    await db.execute(
        sql_text("DELETE FROM chunks WHERE document_id = :doc_id AND chunk_index = 0"),
        {"doc_id": str(doc_id)},
    )
    await db.execute(
        sql_text("""
            INSERT INTO chunks (user_id, document_id, chunk_index, text, embedding)
            VALUES (:user_id, :document_id, 0, :text, CAST(:embedding AS vector))
        """),
        {
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "text": note_chunk_text,
            "embedding": note_emb_str,
        },
    )
    await db.commit()

    logger.info(
        "vectorizer.note_chunk_revectorized",
        doc_id=str(doc_id),
        mention_count=len(mention_names),
    )
    return True
