"""Chat endpoint — SSE streaming with document-scoped or cross-document retrieval."""

from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.deps import DbSession

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    user_id: str
    document_id: str | None = None  # None = cross-document
    scope: str = "document"  # "document" or "all"


@router.post("/chat")
async def chat(req: ChatRequest, db: DbSession) -> StreamingResponse:
    """Stream a chat response with citations via SSE."""
    from app.services.chat.retriever import (
        retrieve_cross_document_chunks,
        retrieve_document_chunks,
    )
    from app.services.chat.responder import stream_response

    user_id = UUID(req.user_id)
    kg_context = None

    if req.scope == "document" and req.document_id:
        # Single-document chat
        chunks = await retrieve_document_chunks(
            db, UUID(req.document_id), req.question
        )
    else:
        # Cross-document chat — try KG lookup first
        kg_context = await _kg_lookup(db, user_id, req.question)
        chunks = await retrieve_cross_document_chunks(
            db, user_id, req.question
        )

    return StreamingResponse(
        stream_response(req.question, chunks, req.scope, kg_context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def _kg_lookup(db: DbSession, user_id: UUID, question: str) -> str | None:
    """Try to answer from knowledge graph facts before falling back to retrieval."""
    from sqlalchemy import text

    # Simple heuristic: extract potential entity/fact terms from the question
    # Look for facts matching keywords in the question
    result = await db.execute(
        text("""
            SELECT e.canonical_name, f.field_name, f.field_value
            FROM facts f
            JOIN entities e ON e.id = f.entity_id
            WHERE f.user_id = :uid AND f.valid_until IS NULL
            ORDER BY f.created_at DESC
            LIMIT 50
        """),
        {"uid": str(user_id)},
    )
    facts = result.fetchall()

    if not facts:
        return None

    # Filter facts that seem relevant to the question
    q_lower = question.lower()
    relevant = []
    for row in facts:
        entity_name = row[0].lower()
        field_name = row[1].lower().replace("_", " ")
        if entity_name in q_lower or field_name in q_lower:
            relevant.append(f"{row[0]} — {row[1]}: {row[2]}")

    if not relevant:
        return None

    return "\n".join(relevant)
