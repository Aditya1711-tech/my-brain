from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EntitiesRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_candidates(
        self,
        user_id: UUID,
        names: list[str],
        identifiers: dict,
        dob: str | None = None,
    ) -> list[dict]:
        """Find candidate entities via trigram (≥0.5) + phonetic + identifier + DOB cross-ref."""
        if not names and not identifiers and not dob:
            return []

        from metaphone import doublemetaphone

        conditions = []
        params: dict = {"user_id": str(user_id)}

        for i, name in enumerate(names):
            # Trigram similarity (raised from 0.3 → 0.5 to reduce false positives)
            params[f"name_{i}"] = name
            conditions.append(f"similarity(e.canonical_name, :name_{i}) > 0.5")

            # Alias substring match
            params[f"alias_{i}"] = f"%{name}%"
            conditions.append(f"e.aliases::text ILIKE :alias_{i}")

            # Phonetic (double-metaphone primary code)
            primary, _ = doublemetaphone(name or "")
            if primary:
                params[f"metaphone_{i}"] = primary
                conditions.append(f"e.name_metaphone = :metaphone_{i}")

        # Identifier exact matches
        for key, value in identifiers.items():
            params[f"ident_{key}"] = value
            conditions.append(f"e.identifiers->>'{key}' = :ident_{key}")

        # DOB cross-reference via facts subquery
        if dob:
            params["dob"] = dob
            conditions.append(
                "EXISTS ("
                "  SELECT 1 FROM facts f"
                "  WHERE f.entity_id = e.id"
                "    AND f.field_name = 'date_of_birth'"
                "    AND f.field_value = :dob"
                ")"
            )

        where_clause = " OR ".join(conditions) if conditions else "false"

        result = await self.db.execute(
            text(f"""
                SELECT
                    e.id,
                    e.entity_type,
                    e.canonical_name,
                    e.aliases,
                    e.attributes,
                    e.identifiers,
                    (
                        SELECT COALESCE(array_agg(DISTINCT d.doc_type), ARRAY[]::text[])
                        FROM document_entities de
                        JOIN documents d ON d.id = de.document_id
                        WHERE de.entity_id = e.id AND de.user_id = :user_id
                    ) AS linked_doc_types
                FROM entities e
                WHERE e.user_id = :user_id
                  AND e.deleted_at IS NULL
                  AND ({where_clause})
                LIMIT 50
            """),
            params,
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def create(
        self,
        user_id: UUID,
        entity_type: str,
        canonical_name: str,
        aliases: list[str] | None = None,
        attributes: dict | None = None,
        identifiers: dict | None = None,
    ) -> str:
        """Create a new entity and return its ID."""
        import json

        from metaphone import doublemetaphone
        primary, _ = doublemetaphone(canonical_name or "")
        name_metaphone = primary or None

        result = await self.db.execute(
            text("""
                INSERT INTO entities (user_id, entity_type, canonical_name, aliases, attributes, identifiers, name_metaphone)
                VALUES (:user_id, :entity_type, :canonical_name, CAST(:aliases AS jsonb), CAST(:attributes AS jsonb), CAST(:identifiers AS jsonb), :name_metaphone)
                RETURNING id
            """),
            {
                "user_id": str(user_id),
                "entity_type": entity_type,
                "canonical_name": canonical_name,
                "aliases": json.dumps(aliases or []),
                "attributes": json.dumps(attributes or {}),
                "identifiers": json.dumps(identifiers or {}),
                "name_metaphone": name_metaphone,
            },
        )
        row = result.fetchone()
        return str(row[0])  # type: ignore[index]

    async def add_aliases(self, entity_id: str, aliases: list[str]) -> None:
        """Append new aliases to an existing entity (deduplicates)."""
        import json

        await self.db.execute(
            text("""
                UPDATE entities
                SET aliases = (
                    SELECT jsonb_agg(DISTINCT val)
                    FROM jsonb_array_elements_text(aliases || CAST(:new_aliases AS jsonb)) AS val
                ),
                updated_at = now()
                WHERE id = :entity_id
            """),
            {
                "entity_id": entity_id,
                "new_aliases": json.dumps(aliases),
            },
        )

    async def update_identifiers(self, entity_id: str, identifiers: dict) -> None:
        """Merge new identifiers into existing entity."""
        import json

        await self.db.execute(
            text("""
                UPDATE entities
                SET identifiers = identifiers || CAST(:new_identifiers AS jsonb),
                    updated_at = now()
                WHERE id = :entity_id
            """),
            {
                "entity_id": entity_id,
                "new_identifiers": json.dumps(identifiers),
            },
        )

    async def link_document(
        self, document_id: UUID, entity_id: str, user_id: UUID, role: str
    ) -> None:
        """Create a document_entities junction row."""
        await self.db.execute(
            text("""
                INSERT INTO document_entities (document_id, entity_id, user_id, role)
                VALUES (:document_id, :entity_id, :user_id, :role)
                ON CONFLICT (document_id, entity_id, role) DO NOTHING
            """),
            {
                "document_id": str(document_id),
                "entity_id": entity_id,
                "user_id": str(user_id),
                "role": role,
            },
        )

    async def create_relationship(
        self,
        user_id: UUID,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
    ) -> None:
        """Create an entity relationship (idempotent)."""
        await self.db.execute(
            text("""
                INSERT INTO entity_relationships (user_id, from_entity_id, to_entity_id, relation_type)
                VALUES (:user_id, :from_entity_id, :to_entity_id, :relation_type)
                ON CONFLICT (user_id, from_entity_id, to_entity_id, relation_type) DO NOTHING
            """),
            {
                "user_id": str(user_id),
                "from_entity_id": from_entity_id,
                "to_entity_id": to_entity_id,
                "relation_type": relation_type,
            },
        )
