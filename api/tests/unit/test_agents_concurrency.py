"""Regression test for D-AGENT-01: agent singleton concurrency bug.

Verifies that agents have no mutable instance state and that
concurrent run() calls don't cross-contaminate page images.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.classifier import ClassifierAgent, ClassifierInput
from app.agents.extractor import ExtractorAgent, ExtractorInput


# -- Helpers ------------------------------------------------------------------

def _make_mock_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Build a fake Anthropic response with a single tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input
    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=100, output_tokens=50)
    return resp


# -- Tests: no mutable state --------------------------------------------------

def test_classifier_has_no_instance_state():
    """ClassifierAgent must not store per-request data on self."""
    agent = ClassifierAgent()
    assert not hasattr(agent, "_page_image"), (
        "ClassifierAgent still has _page_image instance state (D-AGENT-01)"
    )


def test_extractor_has_no_instance_state():
    """ExtractorAgent must not store per-request data on self."""
    agent = ExtractorAgent()
    assert not hasattr(agent, "_page_images"), (
        "ExtractorAgent still has _page_images instance state (D-AGENT-01)"
    )


# -- Tests: no module-level singletons ----------------------------------------

def test_no_module_level_classifier_singleton():
    """classifier_agent singleton must not exist at module level."""
    import app.agents.classifier as mod
    assert not hasattr(mod, "classifier_agent"), (
        "Module-level classifier_agent singleton still exists (D-AGENT-01)"
    )


def test_no_module_level_extractor_singleton():
    """extractor_agent singleton must not exist at module level."""
    import app.agents.extractor as mod
    assert not hasattr(mod, "extractor_agent"), (
        "Module-level extractor_agent singleton still exists (D-AGENT-01)"
    )


# -- Tests: concurrent calls get correct images -------------------------------

@pytest.mark.asyncio
async def test_classifier_concurrent_calls_isolated():
    """Two concurrent classifier calls must each see their own page_image."""
    classifier_output = {
        "document_type": "passport",
        "domain": "personal",
        "country": "IN",
        "primary_language": "en",
        "is_scanned": False,
        "is_handwritten": False,
        "is_digital": True,
        "has_clear_text": True,
        "entity_hints": [],
    }

    images_seen: list[bytes | None] = []

    original_build = ClassifierAgent._build_messages

    def spy_build(self, input_data, **kwargs):
        images_seen.append(kwargs.get("page_image"))
        return original_build(self, input_data, **kwargs)

    mock_resp = _make_mock_response("ClassifierOutput", classifier_output)

    with (
        patch.object(ClassifierAgent, "_build_messages", spy_build),
        patch("app.agents.base.anthropic_client") as mock_client,
        patch("app.agents.base.langfuse") as mock_langfuse,
    ):
        mock_langfuse.enabled = False
        mock_client.messages.create = AsyncMock(return_value=mock_resp)

        img_a = b"IMAGE_A_DATA"
        img_b = b"IMAGE_B_DATA"

        input_a = ClassifierInput(text_sample="doc A text", has_image=True)
        input_b = ClassifierInput(text_sample="doc B text", has_image=True)

        # Run two calls concurrently on separate agent instances
        await asyncio.gather(
            ClassifierAgent().run(input_a, page_image=img_a),
            ClassifierAgent().run(input_b, page_image=img_b),
        )

    assert len(images_seen) == 2
    assert images_seen[0] == img_a, "First call should see image A"
    assert images_seen[1] == img_b, "Second call should see image B"


@pytest.mark.asyncio
async def test_extractor_concurrent_calls_isolated():
    """Two concurrent extractor calls must each see their own page_images."""
    extractor_output = {
        "fields": [{"name": "test", "value": "val"}],
        "detected_entities": [],
    }

    images_seen: list[list[bytes]] = []

    original_build = ExtractorAgent._build_messages

    def spy_build(self, input_data, **kwargs):
        images_seen.append(kwargs.get("page_images") or [])
        return original_build(self, input_data, **kwargs)

    mock_resp = _make_mock_response("ExtractionOutput", extractor_output)

    with (
        patch.object(ExtractorAgent, "_build_messages", spy_build),
        patch("app.agents.base.anthropic_client") as mock_client,
        patch("app.agents.base.langfuse") as mock_langfuse,
    ):
        mock_langfuse.enabled = False
        mock_client.messages.create = AsyncMock(return_value=mock_resp)

        imgs_a = [b"PAGE_1_A", b"PAGE_2_A"]
        imgs_b = [b"PAGE_1_B"]

        input_a = ExtractorInput(
            schema_fields=[], document_type="passport", text="doc A", has_images=True,
        )
        input_b = ExtractorInput(
            schema_fields=[], document_type="invoice", text="doc B", has_images=True,
        )

        await asyncio.gather(
            ExtractorAgent().run(input_a, page_images=imgs_a),
            ExtractorAgent().run(input_b, page_images=imgs_b),
        )

    assert len(images_seen) == 2
    assert images_seen[0] == imgs_a, "First call should see images A"
    assert images_seen[1] == imgs_b, "Second call should see images B"
