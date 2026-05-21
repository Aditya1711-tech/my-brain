from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FactsRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert(
        self,
        user_id: UUID,
        entity_id: str,
        source_document_id: UUID,
        field_name: str,
        field_value: str,
        field_type: str,
        confidence: float,
    ) -> None:
        """Insert a new fact, superseding any existing current fact for the same field.

        Fact versioning: if entity already has a current fact (valid_until IS NULL)
        with the same field_name, set its valid_until = now() before inserting new one.
        """
        # Supersede existing current fact
        await self.db.execute(
            text("""
                UPDATE facts
                SET valid_until = now()
                WHERE user_id = :user_id
                  AND entity_id = :entity_id
                  AND field_name = :field_name
                  AND valid_until IS NULL
            """),
            {
                "user_id": str(user_id),
                "entity_id": entity_id,
                "field_name": field_name,
            },
        )

        # Insert new current fact
        await self.db.execute(
            text("""
                INSERT INTO facts
                    (user_id, entity_id, source_document_id, field_name,
                     field_value, field_type, confidence)
                VALUES
                    (:user_id, :entity_id, :source_document_id, :field_name,
                     :field_value, :field_type, :confidence)
            """),
            {
                "user_id": str(user_id),
                "entity_id": entity_id,
                "source_document_id": str(source_document_id),
                "field_name": field_name,
                "field_value": field_value,
                "field_type": field_type,
                "confidence": confidence,
            },
        )

    async def get_current_by_entity(self, entity_id: str) -> list[dict]:
        """Get all current (non-superseded) facts for an entity."""
        result = await self.db.execute(
            text("""
                SELECT id, field_name, field_value, field_type, confidence,
                       source_document_id, valid_from, created_at
                FROM facts
                WHERE entity_id = :entity_id AND valid_until IS NULL
                ORDER BY field_name
            """),
            {"entity_id": entity_id},
        )
        return [dict(row) for row in result.mappings().fetchall()]
