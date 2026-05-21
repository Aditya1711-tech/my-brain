"""Retrieve relevant chunks for chat context."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.openai_embeddings import get_embeddings


async def retrieve_document_chunks(
    db: AsyncSession,
    document_id: UUID,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Vector search within a single document's chunks."""
    embeddings = await get_embeddings([query])
    query_embedding = embeddings[0]
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    result = await db.execute(
        text("""
            SELECT id, chunk_index, text,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks
            WHERE document_id = :doc_id
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """),
        {
            "doc_id": str(document_id),
            "embedding": embedding_str,
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
    top_k: int = 8,
) -> list[dict]:
    """Vector search across all of a user's document chunks."""
    embeddings = await get_embeddings([query])
    query_embedding = embeddings[0]
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    result = await db.execute(
        text("""
            SELECT c.id, c.chunk_index, c.text, c.document_id,
                   d.original_filename,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.user_id = :uid
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """),
        {
            "uid": str(user_id),
            "embedding": embedding_str,
            "top_k": top_k,
        },
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
