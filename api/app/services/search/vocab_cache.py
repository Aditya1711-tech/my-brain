"""Per-user vocabulary cache for search facet resolution.

Process-level cache with 60s TTL per user. Per-key asyncio.Lock
prevents thundering herd on concurrent requests for the same user.
"""

import asyncio
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TTL_SECONDS = 60

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


@dataclass
class _CachedVocab:
    """Cached vocabulary data for a single user."""

    loaded_at: float = 0.0
    file_types: set[str] = field(default_factory=set)
    folder_names: dict[str, str] = field(default_factory=dict)
    tag_names: dict[str, str] = field(default_factory=dict)
    doc_types: set[str] = field(default_factory=set)
    entity_names: dict[str, str] = field(default_factory=dict)
    entity_aliases: dict[str, str] = field(default_factory=dict)
    domains: set[str] = field(default_factory=set)
    relation_types: set[str] = field(default_factory=set)

    @property
    def is_fresh(self) -> bool:
        return (time.monotonic() - self.loaded_at) < TTL_SECONDS


class _VocabStore:
    """Process-level vocab cache. One entry per user, each with a TTL."""

    def __init__(self) -> None:
        self._cache: dict[str, _CachedVocab] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, uid: str) -> asyncio.Lock:
        if uid not in self._locks:
            self._locks[uid] = asyncio.Lock()
        return self._locks[uid]

    async def get(self, db: AsyncSession, user_id: UUID) -> _CachedVocab:
        uid = str(user_id)

        # Fast path: cached and fresh
        cached = self._cache.get(uid)
        if cached and cached.is_fresh:
            return cached

        # Slow path: lock, double-check, load
        async with self._get_lock(uid):
            cached = self._cache.get(uid)
            if cached and cached.is_fresh:
                return cached

            vocab = await _load_vocab(db, uid)
            vocab.loaded_at = time.monotonic()
            self._cache[uid] = vocab
            return vocab


async def _load_vocab(db: AsyncSession, uid: str) -> _CachedVocab:
    """Execute all vocabulary queries and return a populated _CachedVocab."""
    vocab = _CachedVocab()

    # File types
    result = await db.execute(
        text("SELECT DISTINCT file_type FROM documents WHERE user_id = :uid AND deleted_at IS NULL"),
        {"uid": uid},
    )
    vocab.file_types = {r[0] for r in result.fetchall() if r[0]}

    # Folder names
    result = await db.execute(
        text("SELECT id, name FROM folders WHERE user_id = :uid"),
        {"uid": uid},
    )
    vocab.folder_names = {r[1].lower(): str(r[0]) for r in result.fetchall()}

    # Tag names
    result = await db.execute(
        text("SELECT id, name FROM tags WHERE user_id = :uid"),
        {"uid": uid},
    )
    vocab.tag_names = {r[1].lower(): str(r[0]) for r in result.fetchall()}

    # Doc types
    result = await db.execute(
        text("SELECT DISTINCT doc_type FROM documents WHERE user_id = :uid AND doc_type IS NOT NULL AND deleted_at IS NULL"),
        {"uid": uid},
    )
    vocab.doc_types = {r[0] for r in result.fetchall() if r[0]}

    # Domains
    result = await db.execute(
        text("SELECT DISTINCT domain FROM documents WHERE user_id = :uid AND domain IS NOT NULL AND deleted_at IS NULL"),
        {"uid": uid},
    )
    vocab.domains = {r[0] for r in result.fetchall() if r[0]}

    # Entity names + aliases
    result = await db.execute(
        text("SELECT id, canonical_name, aliases FROM entities WHERE user_id = :uid"),
        {"uid": uid},
    )
    for row in result.fetchall():
        eid = str(row[0])
        name = row[1]
        aliases = row[2] if isinstance(row[2], list) else []
        vocab.entity_names[name.lower()] = eid
        for alias in aliases:
            if isinstance(alias, str):
                vocab.entity_aliases[alias.lower()] = eid

    # Relation types in use
    result = await db.execute(
        text("SELECT DISTINCT relation_type FROM entity_relationships WHERE user_id = :uid"),
        {"uid": uid},
    )
    vocab.relation_types = {r[0] for r in result.fetchall() if r[0]}

    return vocab


# Process-level singleton
_store = _VocabStore()


def _reset_store() -> None:
    """Clear the process-level cache. For tests only."""
    _store._cache.clear()
    _store._locks.clear()


class VocabCache:
    """Per-request facade backed by the process-level cache.

    Public interface is unchanged from Phase 1: create per request,
    call load(), access attributes and exact_match(). Internally,
    load() delegates to the process-level _VocabStore with 60s TTL.
    """

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

        cached = await _store.get(self.db, self.user_id)
        self.file_types = cached.file_types
        self.folder_names = cached.folder_names
        self.tag_names = cached.tag_names
        self.doc_types = cached.doc_types
        self.entity_names = cached.entity_names
        self.entity_aliases = cached.entity_aliases
        self.domains = cached.domains
        self.relation_types = cached.relation_types
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
