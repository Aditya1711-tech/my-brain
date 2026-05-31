"""Chat endpoint — SSE streaming with hybrid KG+vector retrieval.

Phase 1.5 rewrite: question router → entity resolution → parallel
KG+vector retrieval → fusion → responder with thread history.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.deps import DbSession, VerifiedUser
from app.repositories.chat_repo import ChatRepo
from app.services.chat.fusion import fuse
from app.services.chat.kg_retriever import resolve_entities, retrieve as kg_retrieve
from app.services.chat.responder import stream_response
from app.services.chat.retriever import (
    retrieve_cross_document_chunks,
    retrieve_document_chunks,
)
from app.services.chat.router import ChatMessage, RoutingHint, classify

logger = structlog.get_logger()

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    thread_id: str | None = None  # None = create new thread
    document_id: str | None = None
    scope: str = "all"  # "all" or "document"


@router.post("/chat")
async def chat(req: ChatRequest, db: DbSession, user_id: VerifiedUser) -> StreamingResponse:
    """Stream a chat response with hybrid KG+vector retrieval and citations."""
    chat_repo = ChatRepo(db)

    # 1. Resolve or create thread
    thread_id = req.thread_id
    if not thread_id:
        title = req.question[:80] if req.question else None
        thread_id = await chat_repo.create_thread(
            user_id,
            scope=req.scope,
            document_id=UUID(req.document_id) if req.document_id else None,
            title=title,
        )
        await db.commit()

    # 2. Load conversation history
    history_rows = await chat_repo.get_messages(thread_id, limit=12)
    history = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in history_rows
    ]

    # 3. Persist user message
    await chat_repo.add_message(thread_id, user_id, "user", req.question)
    await db.commit()

    if req.scope == "document" and req.document_id:
        # Single-doc: vector+BM25 only, no KG, with history
        chunks = await retrieve_document_chunks(
            db, UUID(req.document_id), req.question,
        )
        hint = RoutingHint(
            intent="lookup",
            routing="semantic",
            entity_terms=[],
            field_terms=[],
            time_terms=[],
            refers_to_prior=False,
        )
        context_items = fuse([], chunks, hint)
    else:
        # Cross-doc: full pipeline
        hint = await classify(req.question, history=history)
        resolved = await resolve_entities(db, user_id, hint, history=history)
        entity_ids = [r.entity_id for r in resolved]

        # Sequential KG + vector retrieval (same db session cannot run concurrent queries)
        kg_facts = await kg_retrieve(db, user_id, hint, resolved, history=history)
        chunks = await retrieve_cross_document_chunks(
            db, user_id, req.question, resolved_entity_ids=entity_ids,
        )
        context_items = fuse(kg_facts, chunks, hint)

    return StreamingResponse(
        _stream_and_persist(
            db=db,
            chat_repo=chat_repo,
            thread_id=thread_id,
            user_id=user_id,
            question=req.question,
            context_items=context_items,
            history=history_rows,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Thread-Id": thread_id,
        },
    )


async def _stream_and_persist(
    *,
    db: DbSession,
    chat_repo: ChatRepo,
    thread_id: str,
    user_id: UUID,
    question: str,
    context_items: list,
    history: list[dict],
):
    """Wrap the responder stream — collect full response, then persist."""
    import json

    full_response: list[str] = []
    citations: list[dict] = []

    async for chunk in stream_response(
        question=question,
        context_items=context_items,
        history=history,
    ):
        yield chunk

        # Collect response text and citations for persistence
        try:
            line = chunk.strip()
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("type") == "text_delta":
                    full_response.append(payload["text"])
                elif payload.get("type") in ("kg_fact", "chunk"):
                    citations.append(payload)
        except (json.JSONDecodeError, KeyError):
            pass

    # Persist assistant message
    if full_response:
        await chat_repo.add_message(
            thread_id, user_id, "assistant",
            "".join(full_response),
            citations=citations,
        )
        await db.commit()
