"""Unit tests for the question router (P1.5-D4-CHAT-02).

12 representative questions covering the intent/routing matrix from
05-HYBRID-CHAT.md.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.router import ChatMessage, RoutingHint, classify


def _make_mock_response(hint: dict) -> MagicMock:
    """Build a mock Anthropic response with a RoutingHint tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = hint
    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=100, output_tokens=60)
    return resp


def _hint(**overrides: object) -> dict:
    """Build a valid RoutingHint dict with sensible defaults."""
    base = {
        "intent": "lookup",
        "routing": "factual",
        "entity_terms": [],
        "field_terms": [],
        "time_terms": [],
        "refers_to_prior": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


def test_routing_hint_valid():
    hint = RoutingHint(**_hint())
    assert hint.intent == "lookup"
    assert hint.routing == "factual"


def test_routing_hint_rejects_bad_intent():
    with pytest.raises(Exception):
        RoutingHint(**_hint(intent="invalid"))


def test_routing_hint_rejects_bad_routing():
    with pytest.raises(Exception):
        RoutingHint(**_hint(routing="invalid"))


# ---------------------------------------------------------------------------
# 12 representative questions — verify prompt structure + output parsing
# ---------------------------------------------------------------------------

_CASES = [
    # (question, expected_hint_overrides, description)
    (
        "When does Priya's passport expire?",
        {"intent": "lookup", "routing": "factual", "entity_terms": ["Priya", "passport"], "field_terms": ["expire"]},
        "factual lookup with entity + field",
    ),
    (
        "What was the doctor's recommendation in my last report?",
        {"intent": "lookup", "routing": "semantic", "entity_terms": ["doctor", "report"], "field_terms": ["recommendation"]},
        "semantic lookup — needs chunk text",
    ),
    (
        "Compare my and my wife's passport expiry dates",
        {"intent": "compare", "routing": "mixed", "entity_terms": ["wife", "passport"], "field_terms": ["expiry"]},
        "comparison across entities",
    ),
    (
        "Summarize the marriage certificate",
        {"intent": "summarize", "routing": "semantic", "entity_terms": ["marriage certificate"], "field_terms": []},
        "summarize a document",
    ),
    (
        "And the expiry date?",
        {"intent": "follow_up", "routing": "mixed", "field_terms": ["expiry"], "refers_to_prior": True},
        "follow-up needing history",
    ),
    (
        "List all my documents",
        {"intent": "list", "routing": "mixed", "entity_terms": [], "field_terms": []},
        "list intent",
    ),
    (
        "What is Rahul's date of birth?",
        {"intent": "lookup", "routing": "factual", "entity_terms": ["Rahul"], "field_terms": ["date of birth"]},
        "factual lookup — specific person",
    ),
    (
        "Explain the findings in the x-ray report",
        {"intent": "explain", "routing": "semantic", "entity_terms": ["x-ray report"], "field_terms": ["findings"]},
        "explain intent",
    ),
    (
        "Show me all passports expiring before 2025",
        {"intent": "list", "routing": "factual", "entity_terms": ["passports"], "field_terms": ["expiring"], "time_terms": ["2025"]},
        "list with time filter",
    ),
    (
        "What is it?",
        {"intent": "follow_up", "routing": "mixed", "refers_to_prior": True},
        "pronoun reference — follow-up",
    ),
    (
        "How much was the total on the invoice?",
        {"intent": "lookup", "routing": "factual", "entity_terms": ["invoice"], "field_terms": ["total"]},
        "factual lookup — financial",
    ),
    (
        "Who is the spouse mentioned in the marriage certificate?",
        {"intent": "lookup", "routing": "mixed", "entity_terms": ["spouse", "marriage certificate"], "field_terms": []},
        "entity resolution via relationship",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,expected,desc",
    _CASES,
    ids=[c[2] for c in _CASES],
)
async def test_router_classifies_question(question: str, expected: dict, desc: str):
    """Each question parses correctly from a mock LLM response."""
    hint_dict = _hint(**expected)
    mock_resp = _make_mock_response(hint_dict)

    with patch(
        "app.services.chat.router.create_message",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ):
        result = await classify(question)

    assert isinstance(result, RoutingHint)
    assert result.intent == expected.get("intent", "lookup")
    assert result.routing == expected.get("routing", "factual")


# ---------------------------------------------------------------------------
# History handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_includes_history_in_messages():
    """When history is provided, prior turns appear in the messages array."""
    hint_dict = _hint(intent="follow_up", refers_to_prior=True)
    mock_resp = _make_mock_response(hint_dict)

    history = [
        ChatMessage(role="user", content="When does Priya's passport expire?"),
        ChatMessage(role="assistant", content="Priya's passport expires on 2034-08-15."),
    ]

    with patch(
        "app.services.chat.router.create_message",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock_create:
        await classify("And the issue date?", history=history)

    call_kwargs = mock_create.call_args[1]
    messages = call_kwargs["messages"]
    # history (2) + current question (1) = 3 messages
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["content"] == "And the issue date?"


@pytest.mark.asyncio
async def test_router_caps_history_at_6():
    """Only last 6 history messages are included to limit token usage."""
    hint_dict = _hint()
    mock_resp = _make_mock_response(hint_dict)

    history = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
        for i in range(10)
    ]

    with patch(
        "app.services.chat.router.create_message",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock_create:
        await classify("new question", history=history)

    call_kwargs = mock_create.call_args[1]
    messages = call_kwargs["messages"]
    # 6 history + 1 current = 7
    assert len(messages) == 7


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_fallback_on_no_tool_use():
    """If LLM returns no tool_use block, fallback hint is returned."""
    resp = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    resp.content = [text_block]

    with patch(
        "app.services.chat.router.create_message",
        new_callable=AsyncMock,
        return_value=resp,
    ):
        result = await classify("some question")

    assert result.intent == "lookup"
    assert result.routing == "mixed"


@pytest.mark.asyncio
async def test_router_uses_haiku_model():
    """Router should call create_message with the Haiku model."""
    hint_dict = _hint()
    mock_resp = _make_mock_response(hint_dict)

    with patch(
        "app.services.chat.router.create_message",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock_create:
        await classify("test question")

    call_kwargs = mock_create.call_args[1]
    assert "haiku" in call_kwargs["model"]
