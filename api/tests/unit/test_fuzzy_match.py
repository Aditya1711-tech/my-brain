"""Tests for SearchResolver._fuzzy_match broader coverage (D-FUZZY-MATCH-01).

Verifies trigram fuzzy matching against:
1. Entities (existing)
2. Doc types (existing)
3. Folders (new)
4. Tags (new)
5. Domains (new)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _empty_result():
    """Return a mock DB result with no rows."""
    result = MagicMock()
    result.fetchone.return_value = None
    return result


def _row_result(*values):
    """Return a mock DB result with a single row."""
    row = MagicMock()
    row.__getitem__ = lambda self, idx: values[idx]
    row.__len__ = lambda self: len(values)
    result = MagicMock()
    result.fetchone.return_value = row
    return result


@pytest.fixture(autouse=True)
def reset_vocab_store():
    from app.services.search.vocab_cache import _reset_store

    _reset_store()
    yield
    _reset_store()


def _make_resolver(db_mock):
    """Build a SearchResolver with a mock DB and empty vocab cache."""
    from app.services.search.resolver import SearchResolver

    user_id = uuid4()
    resolver = SearchResolver(db_mock, user_id)
    # Pre-populate vocab as loaded (empty) so _fuzzy_match doesn't trigger load
    resolver.vocab._loaded = True
    return resolver


@pytest.mark.asyncio
async def test_fuzzy_match_entity():
    """Trigram match against entity canonical_name."""
    entity_id = uuid4()
    db = AsyncMock()

    # Entity query returns a match; all others return empty
    call_count = {"n": 0}

    async def route(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:  # entity query (first)
            return _row_result(entity_id, "John Doe", 0.6)
        return _empty_result()

    db.execute = AsyncMock(side_effect=route)

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("Jon Doe")

    assert result is not None
    assert result["facet"] == "entity"
    assert result["value"] == str(entity_id)
    assert result["display"] == "John Doe"


@pytest.mark.asyncio
async def test_fuzzy_match_doc_type():
    """Trigram match against doc_type when entity doesn't match."""
    db = AsyncMock()

    call_count = {"n": 0}

    async def route(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:  # entity query — no match
            return _empty_result()
        if call_count["n"] == 2:  # doc_type query — match
            return _row_result("passport", 0.5)
        return _empty_result()

    db.execute = AsyncMock(side_effect=route)

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("pasport")

    assert result is not None
    assert result["facet"] == "doc_type"
    assert result["value"] == "passport"


@pytest.mark.asyncio
async def test_fuzzy_match_folder():
    """Trigram match against folder name."""
    folder_id = uuid4()
    db = AsyncMock()

    call_count = {"n": 0}

    async def route(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 2:  # entity + doc_type — no match
            return _empty_result()
        if call_count["n"] == 3:  # folder query — match
            return _row_result(folder_id, "Medical Records", 0.45)
        return _empty_result()

    db.execute = AsyncMock(side_effect=route)

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("Medcal Records")

    assert result is not None
    assert result["facet"] == "folder"
    assert result["value"] == str(folder_id)
    assert result["display"] == "Medical Records"


@pytest.mark.asyncio
async def test_fuzzy_match_tag():
    """Trigram match against tag name."""
    tag_id = uuid4()
    db = AsyncMock()

    call_count = {"n": 0}

    async def route(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 3:  # entity + doc_type + folder — no match
            return _empty_result()
        if call_count["n"] == 4:  # tag query — match
            return _row_result(tag_id, "Important", 0.55)
        return _empty_result()

    db.execute = AsyncMock(side_effect=route)

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("Importnt")

    assert result is not None
    assert result["facet"] == "tag"
    assert result["value"] == str(tag_id)
    assert result["display"] == "Important"


@pytest.mark.asyncio
async def test_fuzzy_match_domain():
    """Trigram match against domain."""
    db = AsyncMock()

    call_count = {"n": 0}

    async def route(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 4:  # entity + doc_type + folder + tag — no match
            return _empty_result()
        if call_count["n"] == 5:  # domain query — match
            return _row_result("personal", 0.4)
        return _empty_result()

    db.execute = AsyncMock(side_effect=route)

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("personl")

    assert result is not None
    assert result["facet"] == "domain"
    assert result["value"] == "personal"
    assert result["display"] == "personal"


@pytest.mark.asyncio
async def test_fuzzy_match_no_match():
    """Returns None when no facet matches above threshold."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_empty_result())

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("xyznonexistent")

    assert result is None
    # Should have tried all 5 queries
    assert db.execute.call_count == 5


@pytest.mark.asyncio
async def test_fuzzy_match_priority_order():
    """Entity match takes priority even if folder also matches."""
    entity_id = uuid4()
    db = AsyncMock()

    # Entity matches — should return immediately without trying others
    db.execute = AsyncMock(return_value=_row_result(entity_id, "John Doe", 0.7))

    resolver = _make_resolver(db)
    result = await resolver._fuzzy_match("John")

    assert result is not None
    assert result["facet"] == "entity"
    # Only the entity query should have run (short-circuit)
    assert db.execute.call_count == 1
