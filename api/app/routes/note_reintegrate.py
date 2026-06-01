"""POST /note-reintegrate — re-process a document's note after it is saved.

Called by the Next.js BFF (PATCH /api/documents/[id]/note) in a non-blocking fire-and-forget.
Auth: shared API key (same as /enqueue).
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.deps import DbSession, VerifiedApiKey
from app.integrations.langfuse_client import langfuse
from app.services.notes.mention_resolver import MentionResolver
from app.services.pipeline.vectorizer import revectorize_note_chunk

logger = structlog.get_logger()
router = APIRouter()


class NoteReintegrateRequest(BaseModel):
    doc_id: UUID
    resolved_mentions: list[dict] = []  # [{mention_text: str, entity_id: str}]


@router.post("/note-reintegrate")
async def note_reintegrate(
    body: NoteReintegrateRequest,
    _api_key: VerifiedApiKey,
    db: DbSession,
) -> dict:
    """Re-integrate a document note:
    1. Write note_entity_mentions rows for confirmed @mention picks.
    2. Re-embed note chunk (chunk_index=0) with up-to-date mention names.
    3. Set user_note_indexed_at = now().
    """
    doc_id = body.doc_id
    trace_id = str(doc_id)

    # Load document to get user_id (needed for RLS writes)
    result = await db.execute(
        text("SELECT user_id, user_note FROM documents WHERE id = :doc_id"),
        {"doc_id": str(doc_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    user_id = UUID(str(row[0]))
    user_note = row[1]

    if not user_note:
        return {"ok": True, "mentions_written": 0, "note_chunk_emitted": False}

    # Top-level Langfuse span for this reintegration
    span = None
    if langfuse.enabled:
        try:
            trace = langfuse.trace(id=trace_id, name=f"note-reintegrate-{doc_id}")
            span = trace.span(
                name="note_reintegration",
                input={
                    "doc_id": str(doc_id),
                    "mention_count": len(body.resolved_mentions),
                },
            )
        except (AttributeError, Exception) as exc:
            logger.debug("langfuse_tracing_unavailable", error=str(exc))

    # Step 1: write note_entity_mentions (MentionResolver commits internally)
    mention_resolver = MentionResolver(db)
    mentions_written = await mention_resolver.resolve_and_persist(
        document_id=doc_id,
        user_id=user_id,
        resolved_mentions=body.resolved_mentions,
        trace_id=trace_id,
    )

    # Step 2: re-embed chunk_index=0 (revectorize_note_chunk commits internally)
    note_chunk_emitted = await revectorize_note_chunk(db, doc_id, user_id, trace_id=trace_id)

    # Step 3: mark note as indexed
    await db.execute(
        text("UPDATE documents SET user_note_indexed_at = now() WHERE id = :doc_id"),
        {"doc_id": str(doc_id)},
    )
    await db.commit()

    logger.info(
        "note_reintegrate.complete",
        doc_id=str(doc_id),
        mentions_written=mentions_written,
        note_chunk_emitted=note_chunk_emitted,
    )

    if span:
        try:
            span.end(output={
                "mentions_written": mentions_written,
                "note_chunk_emitted": note_chunk_emitted,
            })
        except (AttributeError, Exception):
            pass

    return {
        "ok": True,
        "mentions_written": mentions_written,
        "note_chunk_emitted": note_chunk_emitted,
    }
