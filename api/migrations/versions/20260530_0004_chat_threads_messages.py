"""Add chat_threads and chat_messages tables with RLS.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── chat_threads ──
    op.execute("""
        CREATE TABLE chat_threads (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            scope text NOT NULL,
            document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
            title text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX idx_chat_threads_user_updated "
        "ON chat_threads(user_id, updated_at DESC);"
    )

    # ── chat_messages ──
    op.execute("""
        CREATE TABLE chat_messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id uuid NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role text NOT NULL,
            content text NOT NULL,
            citations jsonb DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX idx_chat_messages_thread_created "
        "ON chat_messages(thread_id, created_at);"
    )

    # ── RLS: chat_threads (has user_id — direct ownership) ──
    op.execute("ALTER TABLE chat_threads ENABLE ROW LEVEL SECURITY;")
    op.execute(
        'CREATE POLICY "chat_threads_select_own" ON chat_threads '
        "FOR SELECT USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "chat_threads_insert_own" ON chat_threads '
        "FOR INSERT WITH CHECK (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "chat_threads_update_own" ON chat_threads '
        "FOR UPDATE USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "chat_threads_delete_own" ON chat_threads '
        "FOR DELETE USING (user_id = auth.uid());"
    )

    # ── RLS: chat_messages (has user_id — direct ownership) ──
    op.execute("ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;")
    op.execute(
        'CREATE POLICY "chat_messages_select_own" ON chat_messages '
        "FOR SELECT USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "chat_messages_insert_own" ON chat_messages '
        "FOR INSERT WITH CHECK (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "chat_messages_update_own" ON chat_messages '
        "FOR UPDATE USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "chat_messages_delete_own" ON chat_messages '
        "FOR DELETE USING (user_id = auth.uid());"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE;")
    op.execute("DROP TABLE IF EXISTS chat_threads CASCADE;")
