"""Unit tests for the fusion layer (P1.5-D4-CHAT-05) and citation unification (D-CITATIONS-01)."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
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
from app.services.chat.responder import _render_context, stream_response
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


def test_kg_citation_all_fields_populated():
    """KG citation includes entity_id, field_name, and source_document_id."""
    result = fuse([_fact(field_name="dob", field_value="1990-01-15")], [], _hint())
    cit = result[0].citation
    assert cit.type == "kg_fact"
    assert cit.entity_id == _ENTITY_ID
    assert cit.field_name == "dob"
    assert cit.source_document_id == _DOC_ID


def test_chunk_citation_all_fields_populated():
    """Chunk citation includes chunk_id, document_id, and filename."""
    chunk = _chunk(text="passport text")
    result = fuse([], [chunk], _hint(routing="semantic"))
    cit = result[0].citation
    assert cit.type == "chunk"
    assert cit.chunk_id == chunk["id"]
    assert cit.document_id == str(_DOC_ID)
    assert cit.filename == "passport.pdf"


def test_mixed_response_emits_both_citation_types():
    """Mixed fusion produces at least one KG and one chunk citation."""
    facts = [_fact(), _fact(field_name="dob", field_value="1990-01-15")]
    chunks = [_chunk(), _chunk(text="another excerpt", idx=1)]
    result = fuse(facts, chunks, _hint(routing="mixed"))

    kg_types = [r for r in result if r.citation.type == "kg_fact"]
    chunk_types = [r for r in result if r.citation.type == "chunk"]
    assert len(kg_types) >= 1, "Expected at least one KG fact citation"
    assert len(chunk_types) >= 1, "Expected at least one chunk citation"


# ---------------------------------------------------------------------------
# Responder citation emission (D-CITATIONS-01)
# ---------------------------------------------------------------------------


def test_render_context_labels_facts_and_chunks():
    """Context rendering uses [F1] for facts and [C1] for chunks."""
    items = [
        ContextItem(
            type="kg_fact",
            content="Priya — dob: 1990-01-15 (source: passport.pdf)",
            citation=Citation(type="kg_fact"),
            weight=1.0,
        ),
        ContextItem(
            type="chunk",
            content="[from passport.pdf]: some text",
            citation=Citation(type="chunk"),
            weight=0.8,
        ),
        ContextItem(
            type="kg_fact",
            content="Priya — passport_number: A123 (source: passport.pdf)",
            citation=Citation(type="kg_fact"),
            weight=0.9,
        ),
    ]
    rendered = _render_context(items)
    assert "[F1]" in rendered
    assert "[F2]" in rendered
    assert "[C1]" in rendered
    assert rendered.index("[F1]") < rendered.index("[C1]")


@pytest.mark.asyncio
async def test_responder_emits_citations_before_text():
    """SSE stream starts with citation events, then text_delta events."""
    items = fuse([_fact()], [_chunk()], _hint(routing="mixed"))

    # Mock the Anthropic streaming client
    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)

    async def _text_gen():
        yield "Hello"
        yield " world"

    mock_stream.text_stream = _text_gen()

    with patch(
        "app.services.chat.responder.anthropic_client"
    ) as mock_client:
        mock_client.messages.stream.return_value = mock_stream

        events = []
        async for sse in stream_response(
            question="What is the passport number?",
            context_items=items,
        ):
            line = sse.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    # Citation events use the citation's own type field (kg_fact/chunk)
    # because _sse spreads the citation dict which overrides the event type
    citation_events = [e for e in events if e["type"] in ("kg_fact", "chunk")]
    text_events = [e for e in events if e["type"] == "text_delta"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(citation_events) == len(items)
    assert len(text_events) == 2
    assert len(done_events) == 1

    # Verify both types are present
    cit_types = {e["type"] for e in citation_events}
    assert "kg_fact" in cit_types, "Expected a KG fact citation event"
    assert "chunk" in cit_types, "Expected a chunk citation event"

    # Citations appear before text
    first_citation_idx = next(i for i, e in enumerate(events) if e["type"] in ("kg_fact", "chunk"))
    first_text_idx = next(i for i, e in enumerate(events) if e["type"] == "text_delta")
    assert first_citation_idx < first_text_idx
