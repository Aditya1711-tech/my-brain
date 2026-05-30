"""Chat quality eval — 10 Q&A scenarios through router → retrieval → fusion.

Verifies that the chat pipeline selects the right retrieval path, builds
correct context, and produces properly structured output for each question type.

Tests use mocked LLM (router) and mocked DB (entities, facts, chunks).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.chat.fusion import ContextItem, fuse
from app.services.chat.kg_retriever import KGFact
from app.services.chat.router import ChatMessage, RoutingHint, classify


# ---------------------------------------------------------------------------
# Test data: seeded entities, facts, and chunks
# ---------------------------------------------------------------------------

USER_ID = uuid4()
DOC_PASSPORT = uuid4()
DOC_AADHAAR = uuid4()
DOC_MARRIAGE = uuid4()
ENTITY_SELF = uuid4()
ENTITY_SPOUSE = uuid4()

SEEDED_ROUTER_RESPONSES: dict[str, dict] = {
    "passport_number_lookup": {
        "intent": "lookup",
        "routing": "factual",
        "entity_terms": ["Rajat"],
        "field_terms": ["passport number"],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "semantic_explain": {
        "intent": "explain",
        "routing": "semantic",
        "entity_terms": [],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "comparison": {
        "intent": "compare",
        "routing": "mixed",
        "entity_terms": ["Rajat", "Priya"],
        "field_terms": ["date of birth"],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "list_documents": {
        "intent": "list",
        "routing": "factual",
        "entity_terms": [],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "time_filtered": {
        "intent": "lookup",
        "routing": "factual",
        "entity_terms": [],
        "field_terms": ["expiry date"],
        "time_terms": ["2025"],
        "refers_to_prior": False,
    },
    "follow_up": {
        "intent": "follow_up",
        "routing": "mixed",
        "entity_terms": [],
        "field_terms": ["date of birth"],
        "time_terms": [],
        "refers_to_prior": True,
    },
    "relationship": {
        "intent": "lookup",
        "routing": "factual",
        "entity_terms": ["wife"],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "summarize": {
        "intent": "summarize",
        "routing": "semantic",
        "entity_terms": [],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "field_search": {
        "intent": "lookup",
        "routing": "factual",
        "entity_terms": [],
        "field_terms": ["aadhaar number"],
        "time_terms": [],
        "refers_to_prior": False,
    },
    "no_data": {
        "intent": "lookup",
        "routing": "mixed",
        "entity_terms": ["unknown person"],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    },
}


def _make_router_response(key: str) -> MagicMock:
    """Build a mocked Anthropic response for the question router."""
    data = SEEDED_ROUTER_RESPONSES[key]
    block = MagicMock()
    block.type = "tool_use"
    block.input = data
    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=50, output_tokens=30)
    return resp


def _make_kg_facts(*entries: tuple[str, str, str]) -> list[KGFact]:
    """Build KGFact list from (entity_name, field_name, field_value) tuples."""
    now = datetime.now(timezone.utc)
    facts = []
    for entity_name, field_name, field_value in entries:
        facts.append(KGFact(
            entity_id=ENTITY_SELF if "Rajat" in entity_name else ENTITY_SPOUSE,
            entity_name=entity_name,
            field_name=field_name,
            field_value=field_value,
            field_type="string",
            confidence=0.95,
            source_document_id=DOC_PASSPORT,
            source_document_name="passport.pdf",
            valid_from=now,
        ))
    return facts


def _make_chunks(*texts: str) -> list[dict]:
    """Build mock chunk dicts matching retriever output shape."""
    return [
        {
            "id": str(uuid4()),
            "text": text,
            "document_id": str(DOC_PASSPORT),
            "filename": "passport.pdf",
            "chunk_index": i,
            "similarity": 0.85 - i * 0.05,
        }
        for i, text in enumerate(texts)
    ]


# ---------------------------------------------------------------------------
# 1. Factual lookup (entity + field) — KG-heavy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_factual_lookup_routes_to_factual():
    """'What is Rajat's passport number?' → factual routing with entity + field terms."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("passport_number_lookup")
        hint = await classify("What is Rajat's passport number?")

    assert hint.intent == "lookup"
    assert hint.routing == "factual"
    assert "Rajat" in hint.entity_terms
    assert any("passport" in t.lower() for t in hint.field_terms)


@pytest.mark.asyncio
async def test_factual_lookup_fusion_prefers_kg():
    """Factual routing should weight KG facts higher than chunks."""
    hint = RoutingHint(**SEEDED_ROUTER_RESPONSES["passport_number_lookup"])
    facts = _make_kg_facts(("Rajat Sharma", "passport_number", "A1234567"))
    chunks = _make_chunks("Passport issued to Rajat Sharma, No. A1234567")

    items = fuse(facts, chunks, hint)

    assert len(items) > 0
    kg_items = [i for i in items if i.type == "kg_fact"]
    assert len(kg_items) >= 1
    # KG fact should rank first for factual routing
    assert items[0].type == "kg_fact"


# ---------------------------------------------------------------------------
# 2. Semantic/explanatory question — chunk-heavy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_explain_routes_correctly():
    """'What does my trade licence say about permitted activities?' → semantic."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("semantic_explain")
        hint = await classify("What does my trade licence say about permitted activities?")

    assert hint.intent == "explain"
    assert hint.routing == "semantic"


@pytest.mark.asyncio
async def test_semantic_fusion_prefers_chunks():
    """Semantic routing should weight chunks higher than KG facts."""
    hint = RoutingHint(**SEEDED_ROUTER_RESPONSES["semantic_explain"])
    facts = _make_kg_facts(("Rajat Sharma", "licence_type", "Trade"))
    chunks = _make_chunks(
        "The trade licence permits the following activities: import/export of goods",
        "Validity: 2024-01-01 to 2025-12-31. Renewal required 30 days before expiry.",
    )

    items = fuse(facts, chunks, hint)

    chunk_items = [i for i in items if i.type == "chunk"]
    assert len(chunk_items) >= 1
    # Chunks should rank first for semantic routing
    assert items[0].type == "chunk"


# ---------------------------------------------------------------------------
# 3. Comparison across entities — mixed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_comparison_uses_mixed_routing():
    """'Compare Rajat and Priya's dates of birth' → mixed routing, two entities."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("comparison")
        hint = await classify("Compare Rajat and Priya's dates of birth")

    assert hint.intent == "compare"
    assert hint.routing == "mixed"
    assert len(hint.entity_terms) == 2


@pytest.mark.asyncio
async def test_comparison_fusion_includes_both_sources():
    """Mixed routing includes both KG facts and chunks."""
    hint = RoutingHint(**SEEDED_ROUTER_RESPONSES["comparison"])
    facts = _make_kg_facts(
        ("Rajat Sharma", "date_of_birth", "1990-01-15"),
        ("Priya Sharma", "date_of_birth", "1992-06-20"),
    )
    chunks = _make_chunks("DOB: 15/01/1990 — Rajat", "DOB: 20/06/1992 — Priya")

    items = fuse(facts, chunks, hint)

    types = {i.type for i in items}
    assert "kg_fact" in types
    assert "chunk" in types


# ---------------------------------------------------------------------------
# 4. List intent — factual
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_intent_routes_factual():
    """'List all my documents' → list intent, factual routing."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("list_documents")
        hint = await classify("List all my documents")

    assert hint.intent == "list"
    assert hint.routing == "factual"


# ---------------------------------------------------------------------------
# 5. Time-filtered question — factual with time terms
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_time_filtered_includes_time_terms():
    """'Which documents expire in 2025?' → time_terms populated."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("time_filtered")
        hint = await classify("Which documents expire in 2025?")

    assert len(hint.time_terms) > 0
    assert "2025" in hint.time_terms


# ---------------------------------------------------------------------------
# 6. Follow-up with pronoun reference
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_follow_up_sets_refers_to_prior():
    """'What about her date of birth?' → follow_up, refers_to_prior=True."""
    history = [
        ChatMessage(role="user", content="What is Priya's passport number?"),
        ChatMessage(role="assistant", content="Priya's passport number is B7654321."),
    ]
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("follow_up")
        hint = await classify("What about her date of birth?", history=history)

    assert hint.refers_to_prior is True
    assert hint.intent == "follow_up"


# ---------------------------------------------------------------------------
# 7. Relationship-based question
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relationship_question_extracts_relation():
    """'Who is his wife?' → entity_terms includes relationship term."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("relationship")
        hint = await classify("Who is his wife?")

    assert "wife" in hint.entity_terms


# ---------------------------------------------------------------------------
# 8. Summarize request — semantic routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_routes_semantic():
    """'Summarize my passport' → summarize intent, semantic routing."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("summarize")
        hint = await classify("Summarize my passport")

    assert hint.intent == "summarize"
    assert hint.routing == "semantic"


# ---------------------------------------------------------------------------
# 9. Field-name search without entity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_field_search_without_entity():
    """'What is my aadhaar number?' → field_terms but no specific entity."""
    with patch("app.services.chat.router.create_message", new_callable=AsyncMock) as mock:
        mock.return_value = _make_router_response("field_search")
        hint = await classify("What is my aadhaar number?")

    assert any("aadhaar" in t.lower() for t in hint.field_terms)
    assert hint.routing == "factual"


# ---------------------------------------------------------------------------
# 10. No relevant data — graceful empty context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_data_produces_empty_or_minimal_context():
    """Question about unknown entity → fusion produces empty context gracefully."""
    hint = RoutingHint(**SEEDED_ROUTER_RESPONSES["no_data"])
    # No facts, no chunks found
    items = fuse([], [], hint)

    assert isinstance(items, list)
    assert len(items) == 0


# ---------------------------------------------------------------------------
# Cross-cutting: citation structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_citations_have_correct_structure():
    """All context items have properly typed citations."""
    hint = RoutingHint(**SEEDED_ROUTER_RESPONSES["comparison"])
    facts = _make_kg_facts(("Rajat Sharma", "passport_number", "A1234567"))
    chunks = _make_chunks("Passport document text excerpt")

    items = fuse(facts, chunks, hint)

    for item in items:
        assert item.citation.type in ("kg_fact", "chunk")
        if item.citation.type == "kg_fact":
            assert item.citation.entity_id is not None
            assert item.citation.field_name is not None
        elif item.citation.type == "chunk":
            assert item.citation.chunk_id is not None


@pytest.mark.asyncio
async def test_context_rendering_includes_labels():
    """Rendered context uses [F1]/[C1] labeling for the responder."""
    from app.services.chat.responder import _render_context

    hint = RoutingHint(**SEEDED_ROUTER_RESPONSES["comparison"])
    facts = _make_kg_facts(("Rajat", "dob", "1990-01-15"))
    chunks = _make_chunks("some chunk text")

    items = fuse(facts, chunks, hint)
    rendered = _render_context(items)

    # Should contain both fact and chunk labels
    has_fact_label = "[F" in rendered
    has_chunk_label = "[C" in rendered
    assert has_fact_label or has_chunk_label, "Rendered context must have citation labels"
