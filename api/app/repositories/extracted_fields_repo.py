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
        """Insert multiple extracted fields in a single multi-row statement."""
        if not fields:
            return

        value_rows = []
        params: dict = {}
        for i, f in enumerate(fields):
            value_rows.append(
                f"(:uid_{i}, :did_{i}, :fn_{i}, :fv_{i}, :ft_{i}, :c_{i}, :ie_{i})"
            )
            params[f"uid_{i}"] = str(f.user_id)
            params[f"did_{i}"] = str(f.document_id)
            params[f"fn_{i}"] = f.field_name
            params[f"fv_{i}"] = f.field_value
            params[f"ft_{i}"] = f.field_type
            params[f"c_{i}"] = f.confidence
            params[f"ie_{i}"] = f.is_entity_ref

        sql = (
            "INSERT INTO extracted_fields"
            " (user_id, document_id, field_name, field_value, field_type,"
            " confidence, is_entity_ref)"
            f" VALUES {', '.join(value_rows)}"
        )
        await self.db.execute(text(sql), params)
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
        is_grounded: bool | None = None,
        groundedness_method: str | None = None,
        importance: str | None = None,
        retry_budget: int | None = None,
        retry_budget_remaining: int | None = None,
    ) -> None:
        """Update a field with verifier + groundedness results."""
        await self.db.execute(
            text("""
                UPDATE extracted_fields
                SET confidence = :confidence,
                    needs_retry = :needs_retry,
                    reasoning = :reasoning,
                    is_grounded = COALESCE(:is_grounded, is_grounded),
                    groundedness_method = COALESCE(:groundedness_method, groundedness_method),
                    importance = COALESCE(:importance, importance),
                    retry_budget = COALESCE(:retry_budget, retry_budget),
                    retry_budget_remaining = COALESCE(:retry_budget_remaining, retry_budget_remaining)
                WHERE document_id = :document_id AND field_name = :field_name
            """),
            {
                "document_id": str(document_id),
                "field_name": field_name,
                "confidence": confidence,
                "needs_retry": needs_retry,
                "reasoning": reasoning,
                "is_grounded": is_grounded,
                "groundedness_method": groundedness_method,
                "importance": importance,
                "retry_budget": retry_budget,
                "retry_budget_remaining": retry_budget_remaining,
            },
        )
        await self.db.commit()
