"""Tests for VocabCache with process-level TTL (D-VOCAB-CACHE-01).

Verifies:
1. Single DB load under hot loop (no duplicate queries for same user)
2. Reload after TTL expires
3. Different users get separate cache entries
4. exact_match works against cached data
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _mock_db():
    """Build a mock AsyncSession that returns empty results for all vocab queries."""
    mock = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = []
    mock.execute = AsyncMock(return_value=result)
    return mock


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the process-level cache before each test."""
    from app.services.search.vocab_cache import _reset_store

    _reset_store()
    yield
    _reset_store()


@pytest.mark.asyncio
async def test_single_load_under_hot_loop():
    """Multiple load() calls for the same user hit DB only once (7 queries)."""
    from app.services.search.vocab_cache import VocabCache

    db = _mock_db()
    user_id = uuid4()

    # Load 5 times — only the first should hit DB
    for _ in range(5):
        cache = VocabCache(db, user_id)
        await cache.load()

    assert db.execute.call_count == 7, (
        f"Expected 7 DB queries (one load), got {db.execute.call_count}"
    )


@pytest.mark.asyncio
async def test_reload_after_ttl():
    """Cache reloads after TTL expires."""
    from app.services.search.vocab_cache import VocabCache

    db = _mock_db()
    user_id = uuid4()
    current_time = [1000.0]

    with patch("app.services.search.vocab_cache.time") as mock_time:
        mock_time.monotonic = lambda: current_time[0]

        # First load at t=1000
        cache1 = VocabCache(db, user_id)
        await cache1.load()
        assert db.execute.call_count == 7

        # Second load at t=1030 (within TTL) — no reload
        current_time[0] = 1030.0
        cache2 = VocabCache(db, user_id)
        await cache2.load()
        assert db.execute.call_count == 7

        # Third load at t=1061 (after TTL) — reloads
        current_time[0] = 1061.0
        cache3 = VocabCache(db, user_id)
        await cache3.load()
        assert db.execute.call_count == 14, (
            f"Expected 14 DB queries (two loads), got {db.execute.call_count}"
        )


@pytest.mark.asyncio
async def test_different_users_separate_cache():
    """Each user gets their own cache entry."""
    from app.services.search.vocab_cache import VocabCache

    db = _mock_db()
    user_a = uuid4()
    user_b = uuid4()

    cache_a = VocabCache(db, user_a)
    await cache_a.load()
    assert db.execute.call_count == 7

    cache_b = VocabCache(db, user_b)
    await cache_b.load()
    assert db.execute.call_count == 14  # separate load for user_b


@pytest.mark.asyncio
async def test_exact_match_uses_cached_data():
    """exact_match returns correct facet from cached vocabulary."""
    from app.services.search.vocab_cache import VocabCache

    db = AsyncMock()
    user_id = uuid4()

    # Set up mock results for each query in order:
    # file_types, folders, tags, doc_types, domains, entities, relation_types
    call_count = {"n": 0}

    async def ordered_results(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        n = call_count["n"]
        if n == 1:  # file_types
            result.fetchall.return_value = [("pdf",), ("image",)]
        elif n == 2:  # folders
            result.fetchall.return_value = [(uuid4(), "Medical")]
        elif n == 3:  # tags
            result.fetchall.return_value = [(uuid4(), "Important")]
        elif n == 4:  # doc_types
            result.fetchall.return_value = [("passport",), ("aadhaar",)]
        elif n == 5:  # domains
            result.fetchall.return_value = [("personal",)]
        elif n == 6:  # entities
            eid = uuid4()
            result.fetchall.return_value = [(eid, "John Doe", ["JD"])]
        elif n == 7:  # relation_types
            result.fetchall.return_value = [("spouse_of",)]
        else:
            result.fetchall.return_value = []
        return result

    db.execute = AsyncMock(side_effect=ordered_results)

    cache = VocabCache(db, user_id)
    await cache.load()

    # Test exact matches
    assert cache.exact_match("pdf") == {"facet": "file_type", "value": "pdf", "display": "pdf"}
    assert cache.exact_match("passport") == {"facet": "doc_type", "value": "passport", "display": "passport"}
    assert cache.exact_match("personal") == {"facet": "domain", "value": "personal", "display": "personal"}
    assert cache.exact_match("john doe") is not None
    assert cache.exact_match("john doe")["facet"] == "entity"

    # Relation term
    match = cache.exact_match("wife")
    assert match is not None
    assert match["facet"] == "relation"
    assert match["value"] == "spouse_of"

    # No match
    assert cache.exact_match("xyznonexistent") is None


@pytest.mark.asyncio
async def test_cached_data_shared_across_instances():
    """Two VocabCache instances for the same user share the same data."""
    from app.services.search.vocab_cache import VocabCache

    db = AsyncMock()
    user_id = uuid4()

    call_count = {"n": 0}

    async def return_passport(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 4:  # doc_types query
            result.fetchall.return_value = [("passport",)]
        else:
            result.fetchall.return_value = []
        return result

    db.execute = AsyncMock(side_effect=return_passport)

    cache1 = VocabCache(db, user_id)
    await cache1.load()

    # Create second instance — should get same cached data
    cache2 = VocabCache(db, user_id)
    await cache2.load()

    assert cache2.exact_match("passport") is not None
    assert cache2.doc_types == {"passport"}
