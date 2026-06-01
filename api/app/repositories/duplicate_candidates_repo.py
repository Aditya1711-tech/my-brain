from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DuplicateCandidatesRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert(
        self,
        user_id: UUID,
        entity_id_1: str,
        entity_id_2: str,
        confidence: float,
        reason: str,
        ki_reasoning: str | None = None,
    ) -> None:
        """UPSERT a duplicate candidate pair.

        Canonical ordering (entity_id_a < entity_id_b) is enforced here to satisfy
        the CHECK constraint. Confidence is monotonic: GREATEST(existing, new).
        Rows in status 'merged' or 'dismissed' are not updated.
        """
        a, b = sorted([entity_id_1, entity_id_2])
        await self.db.execute(
            text("""
                INSERT INTO entity_duplicate_candidates
                    (user_id, entity_id_a, entity_id_b, confidence, reason, ki_reasoning)
                VALUES (:user_id, :a, :b, :confidence, :reason, :ki_reasoning)
                ON CONFLICT (user_id, entity_id_a, entity_id_b) DO UPDATE
                    SET confidence   = GREATEST(entity_duplicate_candidates.confidence, EXCLUDED.confidence),
                        reason       = EXCLUDED.reason,
                        ki_reasoning = COALESCE(EXCLUDED.ki_reasoning, entity_duplicate_candidates.ki_reasoning),
                        updated_at   = now()
                WHERE entity_duplicate_candidates.status NOT IN ('merged', 'dismissed')
            """),
            {
                "user_id": str(user_id),
                "a": a,
                "b": b,
                "confidence": confidence,
                "reason": reason,
                "ki_reasoning": ki_reasoning,
            },
        )
