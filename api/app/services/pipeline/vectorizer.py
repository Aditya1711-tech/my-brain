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

    # Load document text + summary + extracted fields for enriched chunks
    result = await db.execute(
        sql_text("SELECT raw_text, summary FROM documents WHERE id = :doc_id"),
        {"doc_id": str(doc_id)},
    )
    row = result.fetchone()
    raw_text = row[0] or "" if row else ""  # type: ignore[index]
    summary = row[1] or "" if row else ""  # type: ignore[index]

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

    # Build representative text: summary + fields + raw text
    parts = []
    if summary:
        parts.append(f"Summary: {summary}")
    if field_pairs:
        parts.append("Extracted fields: " + "; ".join(field_pairs))
    if raw_text:
        parts.append(raw_text)

    full_text = "\n\n".join(parts)
    if not full_text.strip():
        logger.info("vectorizer.skip_empty", doc_id=str(doc_id))
        return

    # Chunk
    chunks = chunk_text(full_text)
    if not chunks:
        return

    logger.info("vectorizer.chunking", doc_id=str(doc_id), chunk_count=len(chunks))

    # Embed in batches
    all_embeddings: list[list[float]] = []
    for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
        batch_embeddings = await get_embeddings(batch)
        all_embeddings.extend(batch_embeddings)

    # Insert chunks
    for idx, (chunk_text_val, embedding) in enumerate(zip(chunks, all_embeddings)):
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        await db.execute(
            sql_text("""
                INSERT INTO chunks (user_id, document_id, chunk_index, text, embedding)
                VALUES (:user_id, :document_id, :chunk_index, :text, CAST(:embedding AS vector))
            """),
            {
                "user_id": str(user_id),
                "document_id": str(doc_id),
                "chunk_index": idx,
                "text": chunk_text_val,
                "embedding": embedding_str,
            },
        )

    await db.commit()

    logger.info(
        "vectorizer.complete",
        doc_id=str(doc_id),
        chunks_inserted=len(chunks),
    )

    if span:
        try:
            span.end(output={"chunks_inserted": len(chunks)})
        except (AttributeError, Exception):
            pass
