"""Mention resolver — write note_entity_mentions rows for confirmed @mentions."""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.langfuse_client import langfuse
from app.repositories.entities_repo import EntitiesRepo

logger = structlog.get_logger()


class MentionResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.entities_repo = EntitiesRepo(db)

    async def resolve_and_persist(
        self,
        document_id: UUID,
        user_id: UUID,
        resolved_mentions: list[dict],  # [{mention_text: str, entity_id: str}]
        trace_id: str | None = None,
    ) -> int:
        """Write note_entity_mentions + document_entities rows for confirmed @mentions.

        Idempotent: ON CONFLICT DO UPDATE so re-calling with the same mentions is safe.
        New entities picked via "Create new entity" in the autocomplete are routed through
        entity_resolver.resolve_and_persist() (handled by the /note-reintegrate endpoint,
        ND-B-04) — this service only handles already-resolved picks.

        Returns the number of mention rows written/updated.
        """
        span = None
        if trace_id and langfuse.enabled:
            try:
                trace = langfuse.trace(id=trace_id, name=f"pipeline-{trace_id}")
                span = trace.span(
                    name="mention_resolution",
                    input={
                        "document_id": str(document_id),
                        "mention_count": len(resolved_mentions),
                    },
                )
            except (AttributeError, Exception) as exc:
                logger.debug("langfuse_tracing_unavailable", error=str(exc))

        written = 0

        for mention in resolved_mentions:
            mention_text: str = mention.get("mention_text", "")
            entity_id: str = mention.get("entity_id", "")
            if not mention_text or not entity_id:
                continue

            # UPSERT note_entity_mentions — idempotent on (document_id, entity_id)
            await self.db.execute(
                text("""
                    INSERT INTO note_entity_mentions
                        (user_id, document_id, entity_id, mention_text)
                    VALUES (:user_id, :document_id, :entity_id, :mention_text)
                    ON CONFLICT (document_id, entity_id) DO UPDATE
                        SET mention_text = EXCLUDED.mention_text
                """),
                {
                    "user_id": str(user_id),
                    "document_id": str(document_id),
                    "entity_id": entity_id,
                    "mention_text": mention_text,
                },
            )

            # Also link entity to document with role mentioned_in_note
            await self.entities_repo.link_document(
                document_id=document_id,
                entity_id=entity_id,
                user_id=user_id,
                role="mentioned_in_note",
            )

            written += 1

        await self.db.commit()

        logger.info(
            "mention_resolver.complete",
            document_id=str(document_id),
            mentions_written=written,
        )

        if span:
            try:
                span.end(output={"mentions_written": written})
            except (AttributeError, Exception):
                pass

        return written
