"""Unit tests for the hybrid vector+BM25 retriever (P1.5-D4-CHAT-04).

Mocks DB and embeddings to verify SQL structure, BM25 inclusion,
entity-boost clause, and parameter passing.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.chat.retriever import (
    retrieve_cross_document_chunks,
    retrieve_document_chunks,
)

_USER_ID = uuid4()
_DOC_ID = uuid4()
_ENTITY_ID = uuid4()
_CHUNK_ID = uuid4()

_MOCK_EMBEDDING = [0.1] * 1536


def _mock_db_result(rows: list[tuple]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


def _mock_embeddings():
    return patch(
        "app.services.chat.retriever.get_embeddings",
        new_callable=AsyncMock,
        return_value=[_MOCK_EMBEDDING],
    )


# ---------------------------------------------------------------------------
# Single-doc retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_doc_returns_chunks():
    db = _mock_db_result([
        (str(_CHUNK_ID), 0, "some text", 0.85),
    ])
    with _mock_embeddings():
        chunks = await retrieve_document_chunks(db, _DOC_ID, "test query")

    assert len(chunks) == 1
    assert chunks[0]["text"] == "some text"
    assert chunks[0]["similarity"] == 0.85


@pytest.mark.asyncio
async def test_single_doc_sql_includes_bm25():
    """SQL should contain ts_rank for BM25 scoring."""
    db = _mock_db_result([])
    with _mock_embeddings():
        await retrieve_document_chunks(db, _DOC_ID, "passport expiry")

    sql = str(db.execute.call_args[0][0])
    assert "ts_rank" in sql
    assert "plainto_tsquery" in sql
    assert "combined_score" in sql


@pytest.mark.asyncio
async def test_single_doc_passes_query_param():
    """BM25 needs the query text as a parameter."""
    db = _mock_db_result([])
    with _mock_embeddings():
        await retrieve_document_chunks(db, _DOC_ID, "passport expiry")

    params = db.execute.call_args[0][1]
    assert params["query"] == "passport expiry"


# ---------------------------------------------------------------------------
# Cross-doc retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_doc_returns_chunks():
    db = _mock_db_result([
        (str(_CHUNK_ID), 0, "chunk text", str(_DOC_ID), "passport.pdf", 0.92),
    ])
    with _mock_embeddings():
        chunks = await retrieve_cross_document_chunks(db, _USER_ID, "test")

    assert len(chunks) == 1
    assert chunks[0]["filename"] == "passport.pdf"


@pytest.mark.asyncio
async def test_cross_doc_sql_includes_bm25():
    db = _mock_db_result([])
    with _mock_embeddings():
        await retrieve_cross_document_chunks(db, _USER_ID, "test query")

    sql = str(db.execute.call_args[0][0])
    assert "ts_rank" in sql
    assert "full_text_tsv" in sql
    assert "combined_score" in sql


@pytest.mark.asyncio
async def test_cross_doc_filters_deleted():
    """Cross-doc query should exclude soft-deleted documents."""
    db = _mock_db_result([])
    with _mock_embeddings():
        await retrieve_cross_document_chunks(db, _USER_ID, "test")

    sql = str(db.execute.call_args[0][0])
    assert "deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_cross_doc_entity_boost_included():
    """When entity IDs provided, SQL includes entity-boost subquery."""
    db = _mock_db_result([])
    with _mock_embeddings():
        await retrieve_cross_document_chunks(
            db, _USER_ID, "test", resolved_entity_ids=[_ENTITY_ID],
        )

    sql = str(db.execute.call_args[0][0])
    assert "document_entities" in sql
    assert "entity_boost" in sql or "entity_ids" in sql


@pytest.mark.asyncio
async def test_cross_doc_no_entity_boost_without_ids():
    """Without entity IDs, no entity-boost clause in SQL."""
    db = _mock_db_result([])
    with _mock_embeddings():
        await retrieve_cross_document_chunks(db, _USER_ID, "test")

    sql = str(db.execute.call_args[0][0])
    assert "document_entities" not in sql


@pytest.mark.asyncio
async def test_cross_doc_entity_ids_formatted():
    """Entity IDs should be formatted as a Postgres array string."""
    db = _mock_db_result([])
    eid1, eid2 = uuid4(), uuid4()
    with _mock_embeddings():
        await retrieve_cross_document_chunks(
            db, _USER_ID, "test", resolved_entity_ids=[eid1, eid2],
        )

    params = db.execute.call_args[0][1]
    assert str(eid1) in params["entity_ids"]
    assert str(eid2) in params["entity_ids"]
