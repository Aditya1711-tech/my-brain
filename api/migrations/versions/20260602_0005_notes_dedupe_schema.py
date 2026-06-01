"""Notes + entity-dedupe schema (ND-A-01)

Adds:
- documents.user_note_indexed_at
- entities.name_metaphone, entities.deleted_at
- Partial indices: idx_entities_metaphone, idx_entities_active
- Table: note_entity_mentions (+ RLS)
- Table: entity_duplicate_candidates (+ RLS)
- Trigger: documents_tsv_trigger — recomputes full_text_tsv from
  original_filename + summary + user_note + raw_text on every relevant UPDATE

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── documents: user_note_indexed_at ──
    op.execute("""
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS user_note_indexed_at timestamptz;
    """)

    # ── entities: name_metaphone + deleted_at ──
    op.execute("""
        ALTER TABLE entities
            ADD COLUMN IF NOT EXISTS name_metaphone text,
            ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
    """)

    # Partial index for fast phonetic lookups (NULL rows excluded)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_metaphone
            ON entities(name_metaphone)
            WHERE name_metaphone IS NOT NULL;
    """)

    # Partial index for "active entities only" queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_active
            ON entities(user_id)
            WHERE deleted_at IS NULL;
    """)

    # ── note_entity_mentions ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS note_entity_mentions (
            id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            document_id  uuid        NOT NULL REFERENCES documents(id)  ON DELETE CASCADE,
            entity_id    uuid        NOT NULL REFERENCES entities(id)   ON DELETE CASCADE,
            mention_text text        NOT NULL,
            char_offset  integer,
            created_at   timestamptz NOT NULL DEFAULT now(),
            UNIQUE (document_id, entity_id)
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_note_entity_mentions_entity "
        "ON note_entity_mentions(entity_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_note_entity_mentions_doc "
        "ON note_entity_mentions(document_id);"
    )

    # RLS: note_entity_mentions (has user_id — direct ownership)
    op.execute("ALTER TABLE note_entity_mentions ENABLE ROW LEVEL SECURITY;")
    op.execute(
        'CREATE POLICY "note_entity_mentions_select_own" ON note_entity_mentions '
        "FOR SELECT USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "note_entity_mentions_insert_own" ON note_entity_mentions '
        "FOR INSERT WITH CHECK (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "note_entity_mentions_update_own" ON note_entity_mentions '
        "FOR UPDATE USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "note_entity_mentions_delete_own" ON note_entity_mentions '
        "FOR DELETE USING (user_id = auth.uid());"
    )

    # ── entity_duplicate_candidates ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS entity_duplicate_candidates (
            id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            entity_id_a         uuid        NOT NULL REFERENCES entities(id),
            entity_id_b         uuid        NOT NULL REFERENCES entities(id),
            confidence          float       NOT NULL,
            reason              text        NOT NULL,
            ki_reasoning        text,
            status              text        NOT NULL DEFAULT 'pending',
            auto_merge_eligible boolean     NOT NULL DEFAULT false,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            reviewed_at         timestamptz,
            UNIQUE  (user_id, entity_id_a, entity_id_b),
            CHECK   (entity_id_a < entity_id_b)
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_edc_user_status "
        "ON entity_duplicate_candidates(user_id, status);"
    )

    # RLS: entity_duplicate_candidates (has user_id — direct ownership)
    op.execute("ALTER TABLE entity_duplicate_candidates ENABLE ROW LEVEL SECURITY;")
    op.execute(
        'CREATE POLICY "entity_duplicate_candidates_select_own" ON entity_duplicate_candidates '
        "FOR SELECT USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "entity_duplicate_candidates_insert_own" ON entity_duplicate_candidates '
        "FOR INSERT WITH CHECK (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "entity_duplicate_candidates_update_own" ON entity_duplicate_candidates '
        "FOR UPDATE USING (user_id = auth.uid());"
    )
    op.execute(
        'CREATE POLICY "entity_duplicate_candidates_delete_own" ON entity_duplicate_candidates '
        "FOR DELETE USING (user_id = auth.uid());"
    )

    # ── TSV trigger — recompute full_text_tsv whenever text fields change ──
    #
    # Fires BEFORE INSERT OR UPDATE OF the four text-bearing columns.
    # The trigger's NEW.full_text_tsv assignment overrides any explicit SET
    # in the triggering statement (BEFORE trigger semantics), so the column
    # is always an aggregate of all text fields including user_note.
    op.execute("""
        CREATE OR REPLACE FUNCTION documents_tsv_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.full_text_tsv :=
                to_tsvector('english',
                    COALESCE(NEW.original_filename, '') || ' ' ||
                    COALESCE(NEW.summary, '')           || ' ' ||
                    COALESCE(NEW.user_note, '')         || ' ' ||
                    COALESCE(NEW.raw_text, '')
                );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER documents_tsv_trigger
        BEFORE INSERT OR UPDATE OF original_filename, summary, user_note, raw_text
        ON documents
        FOR EACH ROW EXECUTE FUNCTION documents_tsv_update();
    """)


def downgrade() -> None:
    # Trigger + function
    op.execute("DROP TRIGGER IF EXISTS documents_tsv_trigger ON documents;")
    op.execute("DROP FUNCTION IF EXISTS documents_tsv_update();")

    # Tables (cascades drop their indices, constraints, and RLS policies)
    op.execute("DROP TABLE IF EXISTS entity_duplicate_candidates CASCADE;")
    op.execute("DROP TABLE IF EXISTS note_entity_mentions CASCADE;")

    # Partial indices on entities
    op.execute("DROP INDEX IF EXISTS idx_entities_active;")
    op.execute("DROP INDEX IF EXISTS idx_entities_metaphone;")

    # Columns
    op.execute("ALTER TABLE entities DROP COLUMN IF EXISTS deleted_at;")
    op.execute("ALTER TABLE entities DROP COLUMN IF EXISTS name_metaphone;")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS user_note_indexed_at;")
