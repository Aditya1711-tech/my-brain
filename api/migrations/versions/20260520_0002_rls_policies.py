"""RLS policies — per 04-DATA-MODEL.md

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that have user_id and need per-user RLS
_TABLES_WITH_USER_ID = [
    "folders",
    "tags",
    "documents",
    "extracted_fields",
    "entities",
    "entity_relationships",
    "facts",
    "document_entities",
    "chunks",
    "document_pipeline_events",
]

# Junction tables without user_id — RLS via FK traversal
_JUNCTION_TABLES = [
    "document_tags",
]


def upgrade() -> None:
    for table in _TABLES_WITH_USER_ID:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f'CREATE POLICY "{table}_select_own" ON {table} '
            f"FOR SELECT USING (user_id = auth.uid());"
        )
        op.execute(
            f'CREATE POLICY "{table}_insert_own" ON {table} '
            f"FOR INSERT WITH CHECK (user_id = auth.uid());"
        )
        op.execute(
            f'CREATE POLICY "{table}_update_own" ON {table} '
            f"FOR UPDATE USING (user_id = auth.uid());"
        )
        op.execute(
            f'CREATE POLICY "{table}_delete_own" ON {table} '
            f"FOR DELETE USING (user_id = auth.uid());"
        )

    # document_tags: RLS via document ownership
    op.execute("ALTER TABLE document_tags ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY "document_tags_select_own" ON document_tags
        FOR SELECT USING (
            EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id AND d.user_id = auth.uid())
        );
    """)
    op.execute("""
        CREATE POLICY "document_tags_insert_own" ON document_tags
        FOR INSERT WITH CHECK (
            EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id AND d.user_id = auth.uid())
        );
    """)
    op.execute("""
        CREATE POLICY "document_tags_delete_own" ON document_tags
        FOR DELETE USING (
            EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id AND d.user_id = auth.uid())
        );
    """)


def downgrade() -> None:
    for table in _TABLES_WITH_USER_ID + _JUNCTION_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        # Drop all policies on the table
        op.execute(f"""
            DO $$ DECLARE
                pol record;
            BEGIN
                FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = '{table}'
                LOOP
                    EXECUTE format('DROP POLICY %I ON {table}', pol.policyname);
                END LOOP;
            END $$;
        """)
