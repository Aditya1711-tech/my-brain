"""Shared test fixtures for the my-brain API test suite.

Provides reusable mocks for LLM clients, Supabase, and canned
agent responses so tests don't hit real external services.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# LLM client mocks
# ---------------------------------------------------------------------------

def _make_anthropic_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Build a fake Anthropic response with a single tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input
    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=100, output_tokens=50)
    return resp


@pytest.fixture
def mock_create_message():
    """Patch create_message in the agent base module. Yields the AsyncMock."""
    with patch("app.agents.base.create_message", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_langfuse():
    """Disable Langfuse tracing for tests."""
    with patch("app.agents.base.langfuse") as mock:
        mock.enabled = False
        yield mock


@pytest.fixture
def mock_get_embeddings():
    """Patch get_embeddings to return zero vectors."""
    async def _fake(texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]

    with patch(
        "app.integrations.openai_embeddings.get_embeddings",
        side_effect=_fake,
    ) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Canned agent responses
# ---------------------------------------------------------------------------

@pytest.fixture
def canned_classifier():
    """Canned ClassifierOutput dict for a passport document."""
    return _make_anthropic_response("ClassifierOutput", {
        "document_type": "passport",
        "domain": "personal",
        "country": "IN",
        "primary_language": "en",
        "is_scanned": False,
        "is_handwritten": False,
        "is_digital": True,
        "has_clear_text": True,
        "entity_hints": [
            {"name": "John Doe", "type": "person", "role": "subject"},
        ],
    })


@pytest.fixture
def canned_schema_architect():
    """Canned SchemaOutput dict."""
    return _make_anthropic_response("SchemaOutput", {
        "document_type": "passport",
        "fields": [
            {
                "name": "full_name",
                "field_type": "string",
                "description": "Full name of passport holder",
                "required": True,
                "is_entity_field": True,
                "importance": "critical",
            },
            {
                "name": "passport_number",
                "field_type": "identifier",
                "description": "Passport number",
                "required": True,
                "is_entity_field": False,
                "importance": "critical",
            },
            {
                "name": "date_of_birth",
                "field_type": "date",
                "description": "Date of birth",
                "required": True,
                "is_entity_field": False,
                "importance": "important",
            },
        ],
        "entity_extraction_required": True,
        "notes": None,
    })


@pytest.fixture
def canned_extractor():
    """Canned ExtractionOutput dict."""
    return _make_anthropic_response("ExtractionOutput", {
        "fields": [
            {"name": "full_name", "value": "John Doe", "raw_value": "JOHN DOE"},
            {"name": "passport_number", "value": "A1234567"},
            {"name": "date_of_birth", "value": "1990-01-15"},
        ],
        "detected_entities": [
            {"name": "John Doe", "type": "person", "role": "subject", "fields": {}},
        ],
    })


@pytest.fixture
def canned_verifier():
    """Canned VerificationOutput dict — all fields pass."""
    return _make_anthropic_response("VerificationOutput", {
        "fields": [
            {"field_name": "full_name", "confidence": 0.95, "needs_retry": False, "importance": "critical", "retry_budget": 0, "reasoning": "Matches text"},
            {"field_name": "passport_number", "confidence": 0.98, "needs_retry": False, "importance": "critical", "retry_budget": 0, "reasoning": "Clear identifier"},
            {"field_name": "date_of_birth", "confidence": 0.90, "needs_retry": False, "importance": "important", "retry_budget": 0, "reasoning": "Standard format"},
        ],
        "overall_quality": 0.94,
    })


@pytest.fixture
def canned_knowledge_integrator():
    """Canned IntegrationOutput dict."""
    return _make_anthropic_response("IntegrationOutput", {
        "resolutions": [
            {
                "detected_name": "John Doe",
                "detected_type": "person",
                "decision": "create_new",
                "matched_entity_id": None,
                "new_canonical_name": "John Doe",
                "aliases_to_add": ["JOHN DOE"],
                "reasoning": "No existing match",
            },
        ],
        "facts": [
            {
                "entity_id_placeholder": "John Doe",
                "field_name": "passport_number",
                "field_value": "A1234567",
                "field_type": "identifier",
                "confidence": 0.98,
            },
        ],
        "relationships": [],
    })


@pytest.fixture
def canned_summarizer():
    """Canned SummaryOutput dict."""
    return _make_anthropic_response("SummaryOutput", {
        "summary": "Indian passport issued to John Doe (A1234567), born 15 Jan 1990.",
    })


# ---------------------------------------------------------------------------
# Helper: build a sequence of canned responses for a full pipeline run
# ---------------------------------------------------------------------------

@pytest.fixture
def canned_pipeline_responses(
    canned_classifier,
    canned_schema_architect,
    canned_extractor,
    canned_summarizer,
    canned_verifier,
    canned_knowledge_integrator,
):
    """Return a list of canned responses in pipeline stage order."""
    return [
        canned_classifier,
        canned_schema_architect,
        canned_extractor,
        canned_summarizer,
        canned_verifier,
        canned_knowledge_integrator,
    ]
