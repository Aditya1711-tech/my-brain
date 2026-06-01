"""Unit tests for the KG retriever (P1.5-D4-CHAT-03 / D-KG-CHAT-01).

Tests entity resolution (exact, alias, relation, fuzzy, history) and
fact retrieval with field filtering, time filtering, and deduplication.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.chat.kg_retriever import (
    KGFact,
    ResolvedEntity,
    _dedupe_facts,
    _extract_relation_terms,
    _filter_by_time,
    resolve_entities,
    retrieve,
)
from app.services.chat.router import ChatMessage, RoutingHint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = uuid4()
_ENTITY_PRIYA = uuid4()
_ENTITY_RAHUL = uuid4()
_DOC_PASSPORT = uuid4()


def _hint(**overrides) -> RoutingHint:
    base = {
        "intent": "lookup",
        "routing": "factual",
        "entity_terms": [],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    }
    base.update(overrides)
    return RoutingHint(**base)


def _fact(
    entity_id: UUID | None = None,
    entity_name: str = "Priya",
    field_name: str = "passport_number",
    field_value: str = "A1234567",
    valid_until: datetime | None = None,
) -> KGFact:
    return KGFact(
        entity_id=entity_id or _ENTITY_PRIYA,
        entity_name=entity_name,
        field_name=field_name,
        field_value=field_value,
        field_type="string",
        confidence=0.95,
        source_document_id=_DOC_PASSPORT,
        source_document_name="passport.pdf",
        valid_from=datetime(2026, 1, 1),
        valid_until=valid_until,
    )


class _MockResult:
    """Mock for SQLAlchemy result with mappings()."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self):
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _mock_db(side_effects: list[list[dict]]) -> AsyncMock:
    """Create a mock AsyncSession that returns successive query results."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_MockResult(rows) for rows in side_effects]
    )
    return db


# ---------------------------------------------------------------------------
# Relation term extraction
# ---------------------------------------------------------------------------


def test_extract_relation_terms_wife():
    result = _extract_relation_terms(["wife"])
    assert "spouse" in result
    assert "wife" in result


def test_extract_relation_terms_unknown():
    result = _extract_relation_terms(["passport"])
    assert result == []


def test_extract_relation_terms_multiple():
    result = _extract_relation_terms(["son", "daughter"])
    assert "child" in result


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_exact_match():
    """Exact canonical_name match resolves correctly."""
    db = _mock_db([
        [{"id": str(_ENTITY_PRIYA), "canonical_name": "Priya"}],
    ])
    hint = _hint(entity_terms=["Priya"])
    result = await resolve_entities(db, _USER_ID, hint)

    assert len(result) == 1
    assert result[0].canonical_name == "Priya"
    assert result[0].resolution_path == "exact"


@pytest.mark.asyncio
async def test_resolve_alias_match():
    """Alias match uses 'alias' resolution path."""
    db = _mock_db([
        [{"id": str(_ENTITY_PRIYA), "canonical_name": "Priya Sharma"}],
    ])
    hint = _hint(entity_terms=["Priya"])
    result = await resolve_entities(db, _USER_ID, hint)

    assert len(result) == 1
    assert result[0].resolution_path == "alias"


@pytest.mark.asyncio
async def test_resolve_relation_term():
    """Relation term 'wife' resolves via self entity + relationships."""
    db = _mock_db([
        # 1. Exact match for "wife" — none (it's a relation, not entity)
        [],
        # 2. Find self entity
        [{"id": str(_ENTITY_RAHUL), "canonical_name": "Rahul"}],
        # 3. Related entities via spouse/wife types
        [{"id": str(_ENTITY_PRIYA), "canonical_name": "Priya"}],
    ])
    hint = _hint(entity_terms=["wife"])
    result = await resolve_entities(db, _USER_ID, hint)

    assert len(result) == 1
    assert result[0].canonical_name == "Priya"
    assert result[0].resolution_path == "relation"


@pytest.mark.asyncio
async def test_resolve_fuzzy_fallback():
    """Fuzzy match fires when exact/alias finds nothing."""
    db = _mock_db([
        # 1. Exact match — none
        [],
        # 2. Fuzzy match
        [{"id": str(_ENTITY_PRIYA), "canonical_name": "Priya Sharma", "sim": 0.7}],
    ])
    hint = _hint(entity_terms=["Prya"])  # typo
    result = await resolve_entities(db, _USER_ID, hint)

    assert len(result) == 1
    assert result[0].resolution_path == "fuzzy"


@pytest.mark.asyncio
async def test_resolve_from_history():
    """History-based resolution for follow-up questions."""
    db = _mock_db([
        # 1. Exact match — none (no entity terms)
        # (no queries for exact — entity_terms is empty)
        # 2. History name lookup — finds Priya
        [{"id": str(_ENTITY_PRIYA), "canonical_name": "Priya"}],
    ])
    hint = _hint(refers_to_prior=True, entity_terms=[])
    history = [
        ChatMessage(role="user", content="Tell me about Priya's passport"),
        ChatMessage(role="assistant", content="Priya has passport A1234567."),
    ]
    result = await resolve_entities(db, _USER_ID, hint, history=history)

    assert len(result) == 1
    assert result[0].resolution_path == "history"


@pytest.mark.asyncio
async def test_resolve_deduplicates():
    """Same entity found by multiple paths is not duplicated."""
    db = _mock_db([
        # Exact match returns same entity twice (name + alias)
        [
            {"id": str(_ENTITY_PRIYA), "canonical_name": "Priya"},
            {"id": str(_ENTITY_PRIYA), "canonical_name": "Priya"},
        ],
    ])
    hint = _hint(entity_terms=["Priya"])
    result = await resolve_entities(db, _USER_ID, hint)

    assert len(result) == 1


# ---------------------------------------------------------------------------
# Fact retrieval
# ---------------------------------------------------------------------------

_FACT_ROW = {
    "entity_id": str(_ENTITY_PRIYA),
    "canonical_name": "Priya",
    "field_name": "passport_number",
    "field_value": "A1234567",
    "field_type": "string",
    "confidence": 0.95,
    "source_document_id": str(_DOC_PASSPORT),
    "original_filename": "passport.pdf",
    "valid_from": datetime(2026, 1, 1),
    "valid_until": None,
}


@pytest.mark.asyncio
async def test_retrieve_facts_for_entity():
    """Facts are retrieved for resolved entities."""
    db = _mock_db([[_FACT_ROW]])
    hint = _hint(entity_terms=["Priya"])
    resolved = [ResolvedEntity(
        entity_id=_ENTITY_PRIYA,
        canonical_name="Priya",
        resolution_path="exact",
    )]

    facts = await retrieve(db, _USER_ID, hint, resolved)

    assert len(facts) == 1
    assert facts[0].entity_name == "Priya"
    assert facts[0].field_value == "A1234567"


@pytest.mark.asyncio
async def test_retrieve_with_field_filter():
    """Field terms are passed as SQL LIKE filters."""
    db = _mock_db([[_FACT_ROW]])
    hint = _hint(entity_terms=["Priya"], field_terms=["passport"])
    resolved = [ResolvedEntity(
        entity_id=_ENTITY_PRIYA,
        canonical_name="Priya",
        resolution_path="exact",
    )]

    facts = await retrieve(db, _USER_ID, hint, resolved)
    assert len(facts) == 1

    # Verify field filter was included in the query
    call_args = db.execute.call_args_list[0]
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    # The SQL should contain the field filter parameter
    sql_text = str(call_args[0][0])
    assert "ft_0" in sql_text or "field_name" in sql_text


@pytest.mark.asyncio
async def test_retrieve_field_name_search_no_entity():
    """When no entities resolved, search by field name across all entities."""
    db = _mock_db([[_FACT_ROW]])
    hint = _hint(field_terms=["passport_number"])

    facts = await retrieve(db, _USER_ID, hint, [])

    assert len(facts) == 1


@pytest.mark.asyncio
async def test_retrieve_relation_traversal():
    """Relation terms trigger one-hop traversal."""
    related_fact = {**_FACT_ROW, "entity_id": str(_ENTITY_RAHUL), "canonical_name": "Rahul"}
    db = _mock_db([
        # 1. Facts for Priya
        [_FACT_ROW],
        # 2. Related entities (husband)
        [{"id": str(_ENTITY_RAHUL), "canonical_name": "Rahul"}],
        # 3. Facts for Rahul
        [related_fact],
    ])
    hint = _hint(entity_terms=["Priya", "husband"])
    resolved = [ResolvedEntity(
        entity_id=_ENTITY_PRIYA,
        canonical_name="Priya",
        resolution_path="exact",
    )]

    facts = await retrieve(db, _USER_ID, hint, resolved)

    # Should include facts from both Priya and Rahul
    names = {f.entity_name for f in facts}
    assert "Priya" in names
    assert "Rahul" in names


# ---------------------------------------------------------------------------
# Time filtering
# ---------------------------------------------------------------------------


def test_filter_by_time_year():
    facts = [
        _fact(field_value="2025-08-15"),
        _fact(field_value="2030-12-01"),
    ]
    result = _filter_by_time(facts, ["2025"])
    assert len(result) == 1
    assert "2025" in result[0].field_value


def test_filter_by_time_no_match_returns_all():
    """If time filter removes everything, return original facts."""
    facts = [_fact(field_value="something")]
    result = _filter_by_time(facts, ["2099"])
    assert len(result) == 1  # all returned, not empty


def test_filter_by_time_no_year_in_terms():
    """Non-year time terms (e.g., 'last year') don't filter."""
    facts = [_fact(), _fact(field_name="dob")]
    result = _filter_by_time(facts, ["last year"])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_dedupe_prefers_current():
    facts = [
        _fact(valid_until=datetime(2025, 1, 1)),  # superseded
        _fact(valid_until=None),  # current
    ]
    result = _dedupe_facts(facts)
    assert len(result) == 1
    assert result[0].valid_until is None


def test_dedupe_different_fields_kept():
    facts = [
        _fact(field_name="passport_number"),
        _fact(field_name="date_of_birth"),
    ]
    result = _dedupe_facts(facts)
    assert len(result) == 2


def test_dedupe_different_entities_kept():
    facts = [
        _fact(entity_id=_ENTITY_PRIYA, field_name="dob"),
        _fact(entity_id=_ENTITY_RAHUL, entity_name="Rahul", field_name="dob"),
    ]
    result = _dedupe_facts(facts)
    assert len(result) == 2
