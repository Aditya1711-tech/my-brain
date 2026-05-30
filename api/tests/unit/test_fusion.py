"""Unit tests for the fusion layer (P1.5-D4-CHAT-05)."""

from datetime import datetime
from uuid import uuid4

import pytest

from app.services.chat.fusion import (
    ContextItem,
    Citation,
    _budget_clip,
    _dedupe_overlapping,
    fuse,
)
from app.services.chat.kg_retriever import KGFact
from app.services.chat.router import RoutingHint

_DOC_ID = uuid4()
_ENTITY_ID = uuid4()


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


def _fact(field_name: str = "passport_number", field_value: str = "A1234567") -> KGFact:
    return KGFact(
        entity_id=_ENTITY_ID,
        entity_name="Priya",
        field_name=field_name,
        field_value=field_value,
        field_type="string",
        confidence=0.95,
        source_document_id=_DOC_ID,
        source_document_name="passport.pdf",
        valid_from=datetime(2026, 1, 1),
        valid_until=None,
    )


def _chunk(text: str = "some chunk text", idx: int = 0) -> dict:
    return {
        "id": str(uuid4()),
        "chunk_index": idx,
        "text": text,
        "document_id": str(_DOC_ID),
        "filename": "passport.pdf",
        "similarity": 0.85,
    }


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


def test_fuse_empty():
    result = fuse([], [], _hint())
    assert result == []


def test_fuse_kg_only():
    result = fuse([_fact()], [], _hint(routing="factual"))
    assert len(result) == 1
    assert result[0].type == "kg_fact"
    assert result[0].weight == 1.0


def test_fuse_chunks_only():
    result = fuse([], [_chunk()], _hint(routing="semantic"))
    assert len(result) == 1
    assert result[0].type == "chunk"
    assert result[0].weight == 1.0


def test_fuse_mixed_routing_weights():
    result = fuse([_fact()], [_chunk()], _hint(routing="mixed"))
    kg_items = [r for r in result if r.type == "kg_fact"]
    chunk_items = [r for r in result if r.type == "chunk"]
    assert kg_items[0].weight == 1.0
    assert chunk_items[0].weight == 1.0


def test_fuse_factual_routing_demotes_chunks():
    result = fuse([_fact()], [_chunk()], _hint(routing="factual"))
    chunk_items = [r for r in result if r.type == "chunk"]
    assert chunk_items[0].weight == 0.5


def test_fuse_semantic_routing_demotes_facts():
    result = fuse([_fact()], [_chunk()], _hint(routing="semantic"))
    kg_items = [r for r in result if r.type == "kg_fact"]
    assert kg_items[0].weight == 0.6


def test_fuse_sorted_by_weight():
    result = fuse([_fact()], [_chunk()], _hint(routing="factual"))
    weights = [r.weight for r in result]
    assert weights == sorted(weights, reverse=True)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_dedupe_overlapping_demotes():
    """Chunk containing a fact value gets demoted."""
    items = [
        ContextItem(
            type="kg_fact",
            content="Priya — passport_number: A1234567 (source: passport.pdf)",
            citation=Citation(type="kg_fact", field_name="passport_number"),
            weight=1.0,
        ),
        ContextItem(
            type="chunk",
            content="[from passport.pdf]: Passport number is A1234567",
            citation=Citation(type="chunk"),
            weight=1.0,
        ),
    ]
    result = _dedupe_overlapping(items)
    assert result[0].weight == 1.0  # fact unchanged
    assert result[1].weight == 0.5  # chunk demoted


def test_dedupe_no_overlap_unchanged():
    items = [
        ContextItem(
            type="kg_fact",
            content="Priya — dob: 1990-01-15 (source: passport.pdf)",
            citation=Citation(type="kg_fact"),
            weight=1.0,
        ),
        ContextItem(
            type="chunk",
            content="[from passport.pdf]: Address line text here",
            citation=Citation(type="chunk"),
            weight=1.0,
        ),
    ]
    result = _dedupe_overlapping(items)
    assert result[1].weight == 1.0


# ---------------------------------------------------------------------------
# Budget clipping
# ---------------------------------------------------------------------------


def test_budget_clip_fits():
    items = [
        ContextItem(type="chunk", content="short", citation=Citation(type="chunk"), weight=1.0),
    ]
    result = _budget_clip(items, max_chars=1000)
    assert len(result) == 1


def test_budget_clip_truncates():
    items = [
        ContextItem(type="chunk", content="a" * 500, citation=Citation(type="chunk"), weight=1.0),
        ContextItem(type="chunk", content="b" * 500, citation=Citation(type="chunk"), weight=0.8),
        ContextItem(type="chunk", content="c" * 500, citation=Citation(type="chunk"), weight=0.6),
    ]
    result = _budget_clip(items, max_chars=1100)
    assert len(result) == 2


def test_budget_clip_always_includes_first():
    """Even if first item exceeds budget, it's still included."""
    items = [
        ContextItem(type="chunk", content="x" * 5000, citation=Citation(type="chunk"), weight=1.0),
    ]
    result = _budget_clip(items, max_chars=100)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Citation structure
# ---------------------------------------------------------------------------


def test_fuse_citations_correct_types():
    result = fuse([_fact()], [_chunk()], _hint(routing="mixed"))
    kg_item = [r for r in result if r.type == "kg_fact"][0]
    chunk_item = [r for r in result if r.type == "chunk"][0]

    assert kg_item.citation.type == "kg_fact"
    assert kg_item.citation.entity_id == _ENTITY_ID
    assert chunk_item.citation.type == "chunk"
    assert chunk_item.citation.document_id is not None
