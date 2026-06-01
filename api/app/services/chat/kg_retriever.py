"""KG retriever — entity resolution + fact retrieval for chat.

Resolves natural-language references to entity IDs, then fetches
structured facts from the knowledge graph. Replaces the naive
_kg_lookup in routes/chat.py (fixes D-KG-CHAT-01).
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.router import ChatMessage, RoutingHint

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ResolvedEntity(BaseModel):
    entity_id: UUID
    canonical_name: str
    resolution_path: str  # "exact" | "alias" | "relation" | "fuzzy" | "history"


class KGFact(BaseModel):
    entity_id: UUID
    entity_name: str
    field_name: str
    field_value: str
    field_type: str
    confidence: float
    source_document_id: UUID
    source_document_name: str
    valid_from: datetime
    valid_until: datetime | None = None


# ---------------------------------------------------------------------------
# Relation-term mapping
# ---------------------------------------------------------------------------

_RELATION_TERMS: dict[str, list[str]] = {
    "wife": ["spouse", "wife"],
    "husband": ["spouse", "husband"],
    "spouse": ["spouse", "wife", "husband"],
    "son": ["child", "son", "parent"],
    "daughter": ["child", "daughter", "parent"],
    "child": ["child", "son", "daughter", "parent"],
    "children": ["child", "son", "daughter", "parent"],
    "father": ["parent", "father", "child"],
    "mother": ["parent", "mother", "child"],
    "parent": ["parent", "father", "mother", "child"],
    "brother": ["sibling", "brother"],
    "sister": ["sibling", "sister"],
    "sibling": ["sibling", "brother", "sister"],
}


def _extract_relation_terms(terms: list[str]) -> list[str]:
    """Return relation types that match any of the given terms."""
    matched: set[str] = set()
    for term in terms:
        key = term.lower().strip()
        if key in _RELATION_TERMS:
            matched.update(_RELATION_TERMS[key])
    return list(matched)


# ---------------------------------------------------------------------------
# Entity resolver
# ---------------------------------------------------------------------------


async def resolve_entities(
    db: AsyncSession,
    user_id: UUID,
    hint: RoutingHint,
    history: list[ChatMessage] | None = None,
) -> list[ResolvedEntity]:
    """Resolve entity_terms from the routing hint to actual entity IDs."""
    resolved: list[ResolvedEntity] = []
    seen_ids: set[UUID] = set()

    # 1. Exact / alias match
    for term in hint.entity_terms:
        entities = await _match_exact_or_alias(db, user_id, term)
        for ent in entities:
            eid = UUID(str(ent["id"]))
            if eid not in seen_ids:
                resolved.append(ResolvedEntity(
                    entity_id=eid,
                    canonical_name=ent["canonical_name"],
                    resolution_path="exact" if ent["canonical_name"].lower() == term.lower() else "alias",
                ))
                seen_ids.add(eid)

    # 2. Relation-term resolution (wife/husband/etc.) via "self" entity
    relation_types = _extract_relation_terms(hint.entity_terms)
    if relation_types:
        self_entity = await _find_self_entity(db, user_id)
        if self_entity:
            related = await _related_via_types(db, user_id, UUID(str(self_entity["id"])), relation_types)
            for rel in related:
                eid = UUID(str(rel["id"]))
                if eid not in seen_ids:
                    resolved.append(ResolvedEntity(
                        entity_id=eid,
                        canonical_name=rel["canonical_name"],
                        resolution_path="relation",
                    ))
                    seen_ids.add(eid)

    # 3. Fuzzy match (trigram > 0.5) for unresolved terms
    if not resolved:
        for term in hint.entity_terms:
            entities = await _match_fuzzy(db, user_id, term)
            for ent in entities:
                eid = UUID(str(ent["id"]))
                if eid not in seen_ids:
                    resolved.append(ResolvedEntity(
                        entity_id=eid,
                        canonical_name=ent["canonical_name"],
                        resolution_path="fuzzy",
                    ))
                    seen_ids.add(eid)

    # 4. History-based resolution for follow-ups
    if not resolved and hint.refers_to_prior and history:
        entities = await _resolve_from_history(db, user_id, history)
        for ent in entities:
            eid = UUID(str(ent["id"]))
            if eid not in seen_ids:
                resolved.append(ResolvedEntity(
                    entity_id=eid,
                    canonical_name=ent["canonical_name"],
                    resolution_path="history",
                ))
                seen_ids.add(eid)

    logger.info(
        "entities_resolved",
        count=len(resolved),
        paths=[r.resolution_path for r in resolved],
    )
    return resolved


async def _match_exact_or_alias(
    db: AsyncSession, user_id: UUID, term: str,
) -> list[dict]:
    """Find entities by exact canonical_name or alias match."""
    result = await db.execute(
        text("""
            SELECT id, canonical_name
            FROM entities
            WHERE user_id = :uid
              AND (
                lower(canonical_name) = lower(:term)
                OR aliases::text ILIKE :alias_pat
              )
            LIMIT 5
        """),
        {"uid": str(user_id), "term": term, "alias_pat": f"%{term}%"},
    )
    return [dict(r) for r in result.mappings().fetchall()]


async def _match_fuzzy(
    db: AsyncSession, user_id: UUID, term: str,
) -> list[dict]:
    """Find entities by trigram similarity > 0.5."""
    result = await db.execute(
        text("""
            SELECT id, canonical_name, similarity(canonical_name, :term) AS sim
            FROM entities
            WHERE user_id = :uid
              AND similarity(canonical_name, :term) > 0.5
            ORDER BY sim DESC
            LIMIT 3
        """),
        {"uid": str(user_id), "term": term},
    )
    return [dict(r) for r in result.mappings().fetchall()]


async def _find_self_entity(db: AsyncSession, user_id: UUID) -> dict | None:
    """Find the user's 'self' entity — most subject-role document_entities."""
    result = await db.execute(
        text("""
            SELECT e.id, e.canonical_name
            FROM entities e
            JOIN document_entities de ON de.entity_id = e.id
            WHERE e.user_id = :uid AND de.role = 'subject'
            GROUP BY e.id, e.canonical_name
            ORDER BY count(*) DESC
            LIMIT 1
        """),
        {"uid": str(user_id)},
    )
    row = result.mappings().fetchone()
    return dict(row) if row else None


async def _related_via_types(
    db: AsyncSession,
    user_id: UUID,
    entity_id: UUID,
    relation_types: list[str],
) -> list[dict]:
    """Find entities related to entity_id via any of the given relation types."""
    result = await db.execute(
        text("""
            SELECT DISTINCT e.id, e.canonical_name
            FROM entity_relationships er
            JOIN entities e ON e.id = CASE
                WHEN er.from_entity_id = :eid THEN er.to_entity_id
                ELSE er.from_entity_id
            END
            WHERE er.user_id = :uid
              AND (er.from_entity_id = :eid OR er.to_entity_id = :eid)
              AND er.relation_type = ANY(:rtypes)
        """),
        {
            "uid": str(user_id),
            "eid": str(entity_id),
            "rtypes": relation_types,
        },
    )
    return [dict(r) for r in result.mappings().fetchall()]


async def _resolve_from_history(
    db: AsyncSession,
    user_id: UUID,
    history: list[ChatMessage],
) -> list[dict]:
    """Extract entity names from recent assistant messages and resolve them."""
    # Collect proper nouns from assistant responses (capitalized words, 2+ chars)
    names: set[str] = set()
    for msg in reversed(history[-4:]):
        if msg.role == "assistant":
            words = re.findall(r"\b[A-Z][a-z]{2,}\b", msg.content)
            names.update(words)

    if not names:
        return []

    # Try exact match on each extracted name
    entities: list[dict] = []
    for name in list(names)[:5]:
        matches = await _match_exact_or_alias(db, user_id, name)
        entities.extend(matches)
    return entities


# ---------------------------------------------------------------------------
# KG fact retriever
# ---------------------------------------------------------------------------


async def retrieve(
    db: AsyncSession,
    user_id: UUID,
    hint: RoutingHint,
    resolved_entities: list[ResolvedEntity],
    history: list[ChatMessage] | None = None,
) -> list[KGFact]:
    """Retrieve KG facts based on routing hint and resolved entities."""
    facts: list[KGFact] = []

    # 1. Facts for resolved entities, filtered by field terms
    if resolved_entities:
        for ent in resolved_entities:
            ent_facts = await _facts_for_entity(
                db, user_id, ent.entity_id, hint.field_terms,
            )
            facts.extend(ent_facts)

    # 2. Traverse one hop for relation terms
    relation_types = _extract_relation_terms(hint.entity_terms)
    if relation_types and resolved_entities:
        for ent in resolved_entities:
            related = await _related_via_types(db, user_id, ent.entity_id, relation_types)
            for rel in related:
                rel_facts = await _facts_for_entity(
                    db, user_id, UUID(str(rel["id"])), hint.field_terms,
                )
                facts.extend(rel_facts)

    # 3. Field-name search when no specific entity resolved
    if not resolved_entities and hint.field_terms:
        field_facts = await _facts_by_field_names(db, user_id, hint.field_terms)
        facts.extend(field_facts)

    # 4. Time filter
    if hint.time_terms:
        facts = _filter_by_time(facts, hint.time_terms)

    # Dedupe by (entity_id, field_name) — keep current (valid_until IS NULL) first
    facts = _dedupe_facts(facts)

    logger.info("kg_facts_retrieved", count=len(facts))
    return facts


async def _facts_for_entity(
    db: AsyncSession,
    user_id: UUID,
    entity_id: UUID,
    field_terms: list[str],
) -> list[KGFact]:
    """Get current facts for an entity, optionally filtered by field terms."""
    field_filter = ""
    params: dict = {"uid": str(user_id), "eid": str(entity_id)}

    if field_terms:
        conditions = []
        for i, term in enumerate(field_terms):
            key = f"ft_{i}"
            conditions.append(f"lower(f.field_name) LIKE :{key}")
            params[key] = f"%{term.lower().replace(' ', '_')}%"
        field_filter = "AND (" + " OR ".join(conditions) + ")"

    result = await db.execute(
        text(f"""
            SELECT f.entity_id, e.canonical_name, f.field_name, f.field_value,
                   f.field_type, f.confidence, f.source_document_id,
                   d.original_filename, f.valid_from, f.valid_until
            FROM facts f
            JOIN entities e ON e.id = f.entity_id
            JOIN documents d ON d.id = f.source_document_id
            WHERE f.user_id = :uid
              AND f.entity_id = :eid
              AND f.valid_until IS NULL
              {field_filter}
            ORDER BY f.field_name
        """),
        params,
    )
    return [_row_to_fact(r) for r in result.mappings().fetchall()]


async def _facts_by_field_names(
    db: AsyncSession,
    user_id: UUID,
    field_terms: list[str],
) -> list[KGFact]:
    """Search facts by field name across all entities for a user."""
    conditions = []
    params: dict = {"uid": str(user_id)}
    for i, term in enumerate(field_terms):
        key = f"ft_{i}"
        conditions.append(f"lower(f.field_name) LIKE :{key}")
        params[key] = f"%{term.lower().replace(' ', '_')}%"

    if not conditions:
        return []

    where = " OR ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT f.entity_id, e.canonical_name, f.field_name, f.field_value,
                   f.field_type, f.confidence, f.source_document_id,
                   d.original_filename, f.valid_from, f.valid_until
            FROM facts f
            JOIN entities e ON e.id = f.entity_id
            JOIN documents d ON d.id = f.source_document_id
            WHERE f.user_id = :uid
              AND f.valid_until IS NULL
              AND ({where})
            ORDER BY e.canonical_name, f.field_name
            LIMIT 20
        """),
        params,
    )
    return [_row_to_fact(r) for r in result.mappings().fetchall()]


def _row_to_fact(row: dict) -> KGFact:
    return KGFact(
        entity_id=UUID(str(row["entity_id"])),
        entity_name=row["canonical_name"],
        field_name=row["field_name"],
        field_value=row["field_value"],
        field_type=row["field_type"],
        confidence=float(row["confidence"]),
        source_document_id=UUID(str(row["source_document_id"])),
        source_document_name=row["original_filename"],
        valid_from=row["valid_from"],
        valid_until=row.get("valid_until"),
    )


def _filter_by_time(facts: list[KGFact], time_terms: list[str]) -> list[KGFact]:
    """Keep facts whose values or valid_from contain any time term."""
    if not time_terms:
        return facts

    # Extract years from time terms
    years: set[str] = set()
    for term in time_terms:
        year_matches = re.findall(r"\b(?:19|20)\d{2}\b", term)
        years.update(year_matches)

    if not years:
        # No parseable years — return all facts unfiltered
        return facts

    filtered = []
    for fact in facts:
        # Check if fact value or valid_from year matches
        value_str = str(fact.field_value)
        from_year = str(fact.valid_from.year) if fact.valid_from else ""
        if any(y in value_str or y == from_year for y in years):
            filtered.append(fact)

    # If time filter removed everything, return original (don't over-filter)
    return filtered if filtered else facts


def _dedupe_facts(facts: list[KGFact]) -> list[KGFact]:
    """Dedupe by (entity_id, field_name). Prefer current facts (valid_until IS NULL)."""
    seen: dict[tuple, KGFact] = {}
    for fact in facts:
        key = (fact.entity_id, fact.field_name)
        existing = seen.get(key)
        if existing is None:
            seen[key] = fact
        elif fact.valid_until is None and existing.valid_until is not None:
            # Prefer current over superseded
            seen[key] = fact
    return list(seen.values())
