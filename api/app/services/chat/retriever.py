"""Retrieve relevant chunks for chat context.

Hybrid retrieval: vector cosine similarity + BM25 (ts_rank) with optional
entity-boost for cross-document queries. Phase 1.5 upgrade (P1.5-D4-CHAT-04).
"""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.openai_embeddings import get_embeddings

logger = structlog.get_logger()

# Tunable weights
_BM25_WEIGHT = 0.5
_ENTITY_BOOST = 0.1


def _format_embedding(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def retrieve_document_chunks(
    db: AsyncSession,
    document_id: UUID,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Hybrid vector + BM25 search within a single document's chunks."""
    embeddings = await get_embeddings([query])
    embedding_str = _format_embedding(embeddings[0])

    result = await db.execute(
        text("""
            SELECT id, chunk_index, text,
                   (
                     (1 - (embedding <=> CAST(:embedding AS vector)))
                     + COALESCE(
                         ts_rank(
                           to_tsvector('english', text),
                           plainto_tsquery('english', :query)
                         ), 0
                       ) * :bm25_w
                   ) AS combined_score
            FROM chunks
            WHERE document_id = :doc_id
            ORDER BY combined_score DESC
            LIMIT :top_k
        """),
        {
            "doc_id": str(document_id),
            "embedding": embedding_str,
            "query": query,
            "bm25_w": _BM25_WEIGHT,
            "top_k": top_k,
        },
    )
    return [
        {
            "id": str(row[0]),
            "chunk_index": row[1],
            "text": row[2],
            "similarity": float(row[3]),
        }
        for row in result.fetchall()
    ]


async def retrieve_cross_document_chunks(
    db: AsyncSession,
    user_id: UUID,
    query: str,
    resolved_entity_ids: list[UUID] | None = None,
    top_k: int = 8,
) -> list[dict]:
    """Hybrid vector + BM25 search across all user docs with entity boost."""
    embeddings = await get_embeddings([query])
    embedding_str = _format_embedding(embeddings[0])

    # Entity-boost clause: chunks from docs linked to resolved entities
    boost_clause = ""
    params: dict = {
        "uid": str(user_id),
        "embedding": embedding_str,
        "query": query,
        "bm25_w": _BM25_WEIGHT,
        "top_k": top_k,
    }

    if resolved_entity_ids:
        eid_placeholders = ", ".join(f":eid_{i}" for i in range(len(resolved_entity_ids)))
        boost_clause = f"""
            + CASE WHEN c.document_id IN (
                SELECT document_id FROM document_entities
                WHERE entity_id IN ({eid_placeholders})
              ) THEN :entity_boost ELSE 0.0 END
        """
        for i, eid in enumerate(resolved_entity_ids):
            params[f"eid_{i}"] = str(eid)
        params["entity_boost"] = _ENTITY_BOOST

    result = await db.execute(
        text(f"""
            SELECT c.id, c.chunk_index, c.text, c.document_id,
                   d.original_filename,
                   (
                     (1 - (c.embedding <=> CAST(:embedding AS vector)))
                     + COALESCE(
                         ts_rank(
                           d.full_text_tsv,
                           plainto_tsquery('english', :query)
                         ), 0
                       ) * :bm25_w
                     {boost_clause}
                   ) AS combined_score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.user_id = :uid AND d.deleted_at IS NULL
            ORDER BY combined_score DESC
            LIMIT :top_k
        """),
        params,
    )
    return [
        {
            "id": str(row[0]),
            "chunk_index": row[1],
            "text": row[2],
            "document_id": str(row[3]),
            "filename": row[4],
            "similarity": float(row[5]),
        }
        for row in result.fetchall()
    ]
