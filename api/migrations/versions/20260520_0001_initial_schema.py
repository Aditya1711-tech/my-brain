"""Initial schema — all tables from 04-DATA-MODEL.md

Revision ID: 0001
Revises: None
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")

    # ── folders ──
    op.execute("""
        CREATE TABLE folders (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            parent_id uuid REFERENCES folders(id) ON DELETE CASCADE,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, parent_id, name)
        );
    """)
    op.execute("CREATE INDEX idx_folders_user_parent ON folders(user_id, parent_id);")

    # ── tags ──
    op.execute("""
        CREATE TABLE tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, name)
        );
    """)

    # ── documents ──
    op.execute("""
        CREATE TYPE document_status AS ENUM (
            'uploaded', 'extracting_text', 'classified', 'schema_built',
            'extracted', 'verified', 'integrated', 'vectorized', 'ready', 'failed'
        );
    """)
    op.execute("""
        CREATE TABLE documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            folder_id uuid REFERENCES folders(id) ON DELETE SET NULL,
            file_hash text NOT NULL,
            original_filename text NOT NULL,
            mime_type text NOT NULL,
            file_type text NOT NULL,
            size_bytes bigint NOT NULL,
            storage_path text NOT NULL,
            user_note text,
            status document_status NOT NULL DEFAULT 'uploaded',
            failure_reason text,
            doc_type text,
            domain text,
            country text,
            language text,
            is_scanned boolean,
            is_handwritten boolean,
            schema_json jsonb,
            summary text,
            raw_text text,
            full_text_tsv tsvector,
            metadata jsonb DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            UNIQUE (user_id, file_hash)
        );
    """)
    op.execute("CREATE INDEX idx_documents_user_status ON documents(user_id, status);")
    op.execute("CREATE INDEX idx_documents_user_folder ON documents(user_id, folder_id);")
    op.execute("CREATE INDEX idx_documents_user_file_type ON documents(user_id, file_type);")
    op.execute("CREATE INDEX idx_documents_user_doc_type ON documents(user_id, doc_type);")
    op.execute("CREATE INDEX documents_tsv_idx ON documents USING gin(full_text_tsv);")
    op.execute(
        "CREATE INDEX documents_summary_trgm_idx ON documents USING gin(summary gin_trgm_ops);"
    )

    # ── document_tags ──
    op.execute("""
        CREATE TABLE document_tags (
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (document_id, tag_id)
        );
    """)

    # ── extracted_fields ──
    op.execute("""
        CREATE TABLE extracted_fields (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            field_name text NOT NULL,
            field_value text,
            field_type text NOT NULL,
            confidence numeric(3,2),
            needs_retry boolean DEFAULT false,
            retry_count int DEFAULT 0,
            reasoning text,
            is_entity_ref boolean DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_extracted_fields_doc ON extracted_fields(document_id);")
    op.execute(
        "CREATE INDEX idx_extracted_fields_user_field ON "
        "extracted_fields(user_id, field_name, field_value);"
    )

    # ── entities ──
    op.execute("""
        CREATE TABLE entities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            entity_type text NOT NULL,
            canonical_name text NOT NULL,
            aliases jsonb DEFAULT '[]'::jsonb,
            attributes jsonb DEFAULT '{}'::jsonb,
            identifiers jsonb DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_entities_user_type ON entities(user_id, entity_type);")
    op.execute(
        "CREATE INDEX entities_name_trgm_idx ON entities USING gin(canonical_name gin_trgm_ops);"
    )
    op.execute("CREATE INDEX entities_aliases_gin_idx ON entities USING gin(aliases);")
    op.execute("CREATE INDEX entities_identifiers_gin_idx ON entities USING gin(identifiers);")

    # ── entity_relationships ──
    op.execute("""
        CREATE TABLE entity_relationships (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            from_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            to_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            relation_type text NOT NULL,
            attributes jsonb DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, from_entity_id, to_entity_id, relation_type)
        );
    """)
    op.execute(
        "CREATE INDEX idx_entity_rels_from ON entity_relationships(user_id, from_entity_id);"
    )
    op.execute(
        "CREATE INDEX idx_entity_rels_to ON entity_relationships(user_id, to_entity_id);"
    )

    # ── facts ──
    op.execute("""
        CREATE TABLE facts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            source_document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            field_name text NOT NULL,
            field_value text NOT NULL,
            field_type text NOT NULL,
            confidence numeric(3,2),
            valid_from timestamptz DEFAULT now(),
            valid_until timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_facts_entity_field ON facts(user_id, entity_id, field_name);")
    op.execute(
        "CREATE INDEX idx_facts_current ON facts(user_id, entity_id, field_name, valid_until);"
    )

    # ── document_entities ──
    op.execute("""
        CREATE TABLE document_entities (
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role text NOT NULL,
            PRIMARY KEY (document_id, entity_id, role)
        );
    """)
    op.execute("CREATE INDEX idx_document_entities_entity ON document_entities(entity_id);")

    # ── chunks ──
    op.execute("""
        CREATE TABLE chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index int NOT NULL,
            text text NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb,
            embedding vector(1536) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_chunks_doc ON chunks(document_id, chunk_index);")
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )

    # ── document_pipeline_events ──
    op.execute("""
        CREATE TABLE document_pipeline_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            stage text NOT NULL,
            status text NOT NULL DEFAULT 'success',
            details jsonb DEFAULT '{}'::jsonb,
            trace_id text,
            duration_ms int,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX idx_pipeline_events_doc ON "
        "document_pipeline_events(document_id, created_at);"
    )
    op.execute(
        "CREATE INDEX idx_pipeline_events_user ON "
        "document_pipeline_events(user_id, created_at);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_pipeline_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS document_entities CASCADE;")
    op.execute("DROP TABLE IF EXISTS facts CASCADE;")
    op.execute("DROP TABLE IF EXISTS entity_relationships CASCADE;")
    op.execute("DROP TABLE IF EXISTS entities CASCADE;")
    op.execute("DROP TABLE IF EXISTS extracted_fields CASCADE;")
    op.execute("DROP TABLE IF EXISTS document_tags CASCADE;")
    op.execute("DROP TABLE IF EXISTS documents CASCADE;")
    op.execute("DROP TYPE IF EXISTS document_status;")
    op.execute("DROP TABLE IF EXISTS tags CASCADE;")
    op.execute("DROP TABLE IF EXISTS folders CASCADE;")
