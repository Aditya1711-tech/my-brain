from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EventsRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def insert(
        self,
        user_id: UUID,
        document_id: UUID,
        stage: str,
        status: str = "success",
        details: dict | None = None,
        trace_id: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Record a pipeline event."""
        await self.db.execute(
            text("""
                INSERT INTO document_pipeline_events
                    (user_id, document_id, stage, status, details, trace_id, duration_ms)
                VALUES
                    (:user_id, :document_id, :stage, :status, :details::jsonb, :trace_id, :duration_ms)
            """),
            {
                "user_id": str(user_id),
                "document_id": str(document_id),
                "stage": stage,
                "status": status,
                "details": "{}" if details is None else str(details).replace("'", '"'),
                "trace_id": trace_id,
                "duration_ms": duration_ms,
            },
        )
        await self.db.commit()
