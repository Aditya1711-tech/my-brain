"""Thread endpoints — list, load history, delete."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.deps import DbSession
from app.repositories.chat_repo import ChatRepo

router = APIRouter()


@router.get("/threads")
async def list_threads(user_id: str, db: DbSession) -> list[dict]:
    """List chat threads for a user."""
    repo = ChatRepo(db)
    return await repo.list_threads(UUID(user_id))


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str, user_id: str, db: DbSession,
) -> list[dict]:
    """Load message history for a thread."""
    repo = ChatRepo(db)
    thread = await repo.get_thread(thread_id, UUID(user_id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return await repo.get_messages(thread_id)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str, user_id: str, db: DbSession,
) -> dict:
    """Delete a chat thread and all its messages."""
    repo = ChatRepo(db)
    deleted = await repo.delete_thread(thread_id, UUID(user_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    await db.commit()
    return {"deleted": True}
