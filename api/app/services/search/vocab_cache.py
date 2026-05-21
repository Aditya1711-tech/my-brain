"""Per-user vocabulary cache for search facet resolution."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Common relation terms mapped to relation_type values in entity_relationships
RELATION_TERM_MAP: dict[str, str] = {
    "wife": "spouse_of",
    "husband": "spouse_of",
    "spouse": "spouse_of",
    "son": "child_of",
    "daughter": "child_of",
    "child": "child_of",
    "mother": "parent_of",
    "father": "parent_of",
    "parent": "parent_of",
    "sibling": "sibling_of",
    "brother": "sibling_of",
    "sister": "sibling_of",
    "boss": "manager_of",
    "manager": "manager_of",
    "employee": "member_of",
    "doctor": "patient_of",
    "patient": "patient_of",
    "client": "client_of",
    "owner": "owner_of",
}


class VocabCache:
    """Loads per-user facet vocabulary lazily for search resolution."""

    def __init__(self, db: AsyncSession, user_id: UUID) -> None:
        self.db = db
        self.user_id = user_id
        self._loaded = False
        self.file_types: set[str] = set()
        self.folder_names: dict[str, str] = {}  # name → id
        self.tag_names: dict[str, str] = {}  # name → id
        self.doc_types: set[str] = set()
        self.entity_names: dict[str, str] = {}  # canonical_name → id
        self.entity_aliases: dict[str, str] = {}  # alias → entity_id
        self.domains: set[str] = set()
        self.relation_types: set[str] = set()  # relation_type values in use

    async def load(self) -> None:
        if self._loaded:
            return

        uid = str(self.user_id)

        # File types
        result = await self.db.execute(
            text("SELECT DISTINCT file_type FROM documents WHERE user_id = :uid AND deleted_at IS NULL"),
            {"uid": uid},
        )
        self.file_types = {r[0] for r in result.fetchall() if r[0]}

        # Folder names
        result = await self.db.execute(
            text("SELECT id, name FROM folders WHERE user_id = :uid"),
            {"uid": uid},
        )
        self.folder_names = {r[1].lower(): str(r[0]) for r in result.fetchall()}

        # Tag names
        result = await self.db.execute(
            text("SELECT id, name FROM tags WHERE user_id = :uid"),
            {"uid": uid},
        )
        self.tag_names = {r[1].lower(): str(r[0]) for r in result.fetchall()}

        # Doc types
        result = await self.db.execute(
            text("SELECT DISTINCT doc_type FROM documents WHERE user_id = :uid AND doc_type IS NOT NULL AND deleted_at IS NULL"),
            {"uid": uid},
        )
        self.doc_types = {r[0] for r in result.fetchall() if r[0]}

        # Domains
        result = await self.db.execute(
            text("SELECT DISTINCT domain FROM documents WHERE user_id = :uid AND domain IS NOT NULL AND deleted_at IS NULL"),
            {"uid": uid},
        )
        self.domains = {r[0] for r in result.fetchall() if r[0]}

        # Entity names + aliases
        result = await self.db.execute(
            text("SELECT id, canonical_name, aliases FROM entities WHERE user_id = :uid"),
            {"uid": uid},
        )
        for row in result.fetchall():
            eid = str(row[0])
            name = row[1]
            aliases = row[2] if isinstance(row[2], list) else []
            self.entity_names[name.lower()] = eid
            for alias in aliases:
                if isinstance(alias, str):
                    self.entity_aliases[alias.lower()] = eid

        # Relation types in use
        result = await self.db.execute(
            text("SELECT DISTINCT relation_type FROM entity_relationships WHERE user_id = :uid"),
            {"uid": uid},
        )
        self.relation_types = {r[0] for r in result.fetchall() if r[0]}

        self._loaded = True

    def exact_match(self, term: str) -> dict | None:
        """Try exact/case-insensitive match against all vocabularies."""
        t = term.lower().strip()

        if t in self.file_types:
            return {"facet": "file_type", "value": t, "display": t}

        if t in self.folder_names:
            return {"facet": "folder", "value": self.folder_names[t], "display": t}

        if t in self.tag_names:
            return {"facet": "tag", "value": self.tag_names[t], "display": t}

        # Doc type — also try with underscores
        t_under = t.replace(" ", "_")
        if t in self.doc_types or t_under in self.doc_types:
            matched = t if t in self.doc_types else t_under
            return {"facet": "doc_type", "value": matched, "display": matched.replace("_", " ")}

        if t in self.domains:
            return {"facet": "domain", "value": t, "display": t}

        if t in self.entity_names:
            return {"facet": "entity", "value": self.entity_names[t], "display": t}

        if t in self.entity_aliases:
            return {"facet": "entity", "value": self.entity_aliases[t], "display": t}

        # Relation terms (wife, husband, son, etc.) → resolve to relation_type facet
        if t in RELATION_TERM_MAP:
            rel_type = RELATION_TERM_MAP[t]
            if rel_type in self.relation_types:
                return {"facet": "relation", "value": rel_type, "display": t}

        return None
