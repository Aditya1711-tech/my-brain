"""Chat thread and message persistence."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ChatRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_thread(
        self,
        user_id: UUID,
        scope: str,
        document_id: UUID | None = None,
        title: str | None = None,
    ) -> str:
        """Create a chat thread and return its ID."""
        result = await self.db.execute(
            text("""
                INSERT INTO chat_threads (user_id, scope, document_id, title)
                VALUES (:user_id, :scope, :document_id, :title)
                RETURNING id
            """),
            {
                "user_id": str(user_id),
                "scope": scope,
                "document_id": str(document_id) if document_id else None,
                "title": title,
            },
        )
        row = result.fetchone()
        return str(row[0])  # type: ignore[index]

    async def get_thread(self, thread_id: str, user_id: UUID) -> dict | None:
        """Get a thread by ID (ownership enforced by caller or RLS)."""
        result = await self.db.execute(
            text("""
                SELECT id, user_id, scope, document_id, title, created_at, updated_at
                FROM chat_threads
                WHERE id = :tid AND user_id = :uid
            """),
            {"tid": thread_id, "uid": str(user_id)},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def list_threads(self, user_id: UUID, limit: int = 20) -> list[dict]:
        """List threads for a user, most recently updated first."""
        result = await self.db.execute(
            text("""
                SELECT id, scope, document_id, title, created_at, updated_at
                FROM chat_threads
                WHERE user_id = :uid
                ORDER BY updated_at DESC
                LIMIT :lim
            """),
            {"uid": str(user_id), "lim": limit},
        )
        return [dict(r) for r in result.mappings().fetchall()]

    async def delete_thread(self, thread_id: str, user_id: UUID) -> bool:
        """Delete a thread (cascades to messages). Returns True if deleted."""
        result = await self.db.execute(
            text("""
                DELETE FROM chat_threads
                WHERE id = :tid AND user_id = :uid
            """),
            {"tid": thread_id, "uid": str(user_id)},
        )
        return result.rowcount > 0  # type: ignore[union-attr]

    async def add_message(
        self,
        thread_id: str,
        user_id: UUID,
        role: str,
        content: str,
        citations: list[dict] | None = None,
    ) -> str:
        """Add a message to a thread. Returns message ID."""
        import json

        result = await self.db.execute(
            text("""
                INSERT INTO chat_messages (thread_id, user_id, role, content, citations)
                VALUES (:tid, :uid, :role, :content, CAST(:citations AS jsonb))
                RETURNING id
            """),
            {
                "tid": thread_id,
                "uid": str(user_id),
                "role": role,
                "content": content,
                "citations": json.dumps(citations or []),
            },
        )
        row = result.fetchone()

        # Touch thread updated_at
        await self.db.execute(
            text("UPDATE chat_threads SET updated_at = now() WHERE id = :tid"),
            {"tid": thread_id},
        )

        return str(row[0])  # type: ignore[index]

    async def get_messages(
        self, thread_id: str, limit: int = 12,
    ) -> list[dict]:
        """Get recent messages for a thread, oldest first."""
        result = await self.db.execute(
            text("""
                SELECT id, role, content, citations, created_at
                FROM chat_messages
                WHERE thread_id = :tid
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {"tid": thread_id, "lim": limit},
        )
        rows = [dict(r) for r in result.mappings().fetchall()]
        rows.reverse()  # oldest first
        return rows

    async def update_thread_title(self, thread_id: str, title: str) -> None:
        """Set the thread title (auto-generated from first message)."""
        await self.db.execute(
            text("UPDATE chat_threads SET title = :title WHERE id = :tid"),
            {"tid": thread_id, "title": title},
        )
