"""Unit tests for the summarizer agent (D-SUMMARY-01)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.summarizer import SummarizerAgent, SummarizerInput, SummaryOutput


def _make_mock_response(tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input
    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=50, output_tokens=30)
    return resp


@pytest.mark.asyncio
async def test_summarizer_returns_summary():
    mock_resp = _make_mock_response({
        "summary": "Passport issued to John Doe (A1234567), born 15 Jan 1990.",
    })

    with (
        patch("app.agents.base.create_message", new_callable=AsyncMock, return_value=mock_resp),
        patch("app.agents.base.langfuse") as mock_lf,
    ):
        mock_lf.enabled = False
        input_data = SummarizerInput(
            document_type="passport",
            text_sample="Name: John Doe\nPassport No: A1234567\nDOB: 15/01/1990",
        )
        result = await SummarizerAgent().run(input_data)

    assert isinstance(result, SummaryOutput)
    assert "John Doe" in result.summary
    assert len(result.summary) > 10


@pytest.mark.asyncio
async def test_summarizer_uses_haiku_model():
    """Summarizer should use the cheap Haiku model."""
    agent = SummarizerAgent()
    assert "haiku" in agent.model


def test_summarizer_max_tokens_capped():
    """Output should be capped at 300 tokens for short summaries."""
    agent = SummarizerAgent()
    assert agent.max_tokens == 300
