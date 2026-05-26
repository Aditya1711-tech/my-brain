from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ExtractedFieldCreate:
    def __init__(
        self,
        user_id: UUID,
        document_id: UUID,
        field_name: str,
        field_value: str | None,
        field_type: str,
        confidence: float | None = None,
        is_entity_ref: bool = False,
    ) -> None:
        self.user_id = user_id
        self.document_id = document_id
        self.field_name = field_name
        self.field_value = field_value
        self.field_type = field_type
        self.confidence = confidence
        self.is_entity_ref = is_entity_ref


class ExtractedFieldsRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def bulk_insert(self, fields: list[ExtractedFieldCreate]) -> None:
        """Insert multiple extracted fields at once."""
        if not fields:
            return

        for f in fields:
            await self.db.execute(
                text("""
                    INSERT INTO extracted_fields
                        (user_id, document_id, field_name, field_value, field_type,
                         confidence, is_entity_ref)
                    VALUES
                        (:user_id, :document_id, :field_name, :field_value, :field_type,
                         :confidence, :is_entity_ref)
                """),
                {
                    "user_id": str(f.user_id),
                    "document_id": str(f.document_id),
                    "field_name": f.field_name,
                    "field_value": f.field_value,
                    "field_type": f.field_type,
                    "confidence": f.confidence,
                    "is_entity_ref": f.is_entity_ref,
                },
            )
        await self.db.commit()

    async def get_by_document(
        self, document_id: UUID
    ) -> list[dict]:
        """Get all extracted fields for a document."""
        result = await self.db.execute(
            text("""
                SELECT id, field_name, field_value, field_type, confidence,
                       needs_retry, retry_count, reasoning, is_entity_ref
                FROM extracted_fields
                WHERE document_id = :document_id
                ORDER BY field_name
            """),
            {"document_id": str(document_id)},
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def update_verification(
        self,
        document_id: UUID,
        field_name: str,
        confidence: float,
        needs_retry: bool,
        reasoning: str,
    ) -> None:
        """Update a field with verifier results."""
        await self.db.execute(
            text("""
                UPDATE extracted_fields
                SET confidence = :confidence,
                    needs_retry = :needs_retry,
                    reasoning = :reasoning
                WHERE document_id = :document_id AND field_name = :field_name
            """),
            {
                "document_id": str(document_id),
                "field_name": field_name,
                "confidence": confidence,
                "needs_retry": needs_retry,
                "reasoning": reasoning,
            },
        )
        await self.db.commit()
