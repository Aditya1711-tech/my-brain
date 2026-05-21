from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EntitiesRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_candidates(self, user_id: UUID, names: list[str], identifiers: dict) -> list[dict]:
        """Find candidate entities for resolution via trigram name match + identifier match."""
        if not names and not identifiers:
            return []

        conditions = []
        params: dict = {"user_id": str(user_id)}

        # Trigram name similarity for each detected name
        for i, name in enumerate(names):
            param_key = f"name_{i}"
            conditions.append(f"similarity(canonical_name, :{param_key}) > 0.3")
            params[param_key] = name

        # Also check aliases
        for i, name in enumerate(names):
            param_key = f"alias_{i}"
            conditions.append(f"aliases::text ILIKE :{param_key}")
            params[param_key] = f"%{name}%"

        # Identifier matches (exact)
        for key, value in identifiers.items():
            param_key = f"ident_{key}"
            conditions.append(f"identifiers->>'{key}' = :{param_key}")
            params[param_key] = value

        where_clause = " OR ".join(conditions) if conditions else "false"

        result = await self.db.execute(
            text(f"""
                SELECT id, entity_type, canonical_name, aliases, attributes, identifiers
                FROM entities
                WHERE user_id = :user_id AND ({where_clause})
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

        result = await self.db.execute(
            text("""
                INSERT INTO entities (user_id, entity_type, canonical_name, aliases, attributes, identifiers)
                VALUES (:user_id, :entity_type, :canonical_name, CAST(:aliases AS jsonb), CAST(:attributes AS jsonb), CAST(:identifiers AS jsonb))
                RETURNING id
            """),
            {
                "user_id": str(user_id),
                "entity_type": entity_type,
                "canonical_name": canonical_name,
                "aliases": json.dumps(aliases or []),
                "attributes": json.dumps(attributes or {}),
                "identifiers": json.dumps(identifiers or {}),
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
