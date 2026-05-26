"""Add groundedness, retry-budget columns to extracted_fields;
add processing_state JSONB to documents.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── extracted_fields: groundedness + adaptive retry budget ──
    op.execute("""
        ALTER TABLE extracted_fields
            ADD COLUMN is_grounded BOOLEAN,
            ADD COLUMN groundedness_method TEXT,
            ADD COLUMN importance TEXT,
            ADD COLUMN retry_budget INT DEFAULT 0,
            ADD COLUMN retry_budget_remaining INT DEFAULT 0;
    """)

    # ── documents: processing state for crash resumability ──
    op.execute("""
        ALTER TABLE documents
            ADD COLUMN processing_state JSONB DEFAULT '{}'::jsonb;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE documents
            DROP COLUMN IF EXISTS processing_state;
    """)
    op.execute("""
        ALTER TABLE extracted_fields
            DROP COLUMN IF EXISTS retry_budget_remaining,
            DROP COLUMN IF EXISTS retry_budget,
            DROP COLUMN IF EXISTS importance,
            DROP COLUMN IF EXISTS groundedness_method,
            DROP COLUMN IF EXISTS is_grounded;
    """)
