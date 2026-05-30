"""Unit tests for within-document parallelism (HARNESS-11).

Verifies:
1. classify + summarize run in parallel; summarize failure is non-fatal
2. integrate + vectorize run in parallel; vectorize failure is non-fatal
3. _vectorization_done flag skips redundant vectorization stage
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import _make_anthropic_response


def _make_doc():
    doc = MagicMock()
    doc.id = "doc-123"
    doc.user_id = "user-456"
    doc.status = "extracting_text"
    doc.storage_path = "test.pdf"
    doc.mime_type = "application/pdf"
    doc.original_filename = "test.pdf"
    return doc


def _mock_session():
    session = AsyncMock()
    row = MagicMock()
    row.__getitem__ = lambda self, idx: [
        "Name: John Doe\nPassport No: A1234567",
        "passport",
        "personal",
    ][idx]
    result = MagicMock()
    result.fetchone.return_value = row
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_summarize_failure_nonfatal(mock_create_message, mock_langfuse):
    """If summarizer throws, classification still succeeds and pipeline continues."""
    doc = _make_doc()
    session = _mock_session()

    # Classifier returns valid output; summarizer raises
    classifier_resp = _make_anthropic_response("ClassifierOutput", {
        "document_type": "passport",
        "domain": "personal",
        "country": "IN",
        "primary_language": "en",
        "is_scanned": False,
        "is_handwritten": False,
        "is_digital": True,
        "has_clear_text": True,
        "entity_hints": [],
    })

    call_count = {"n": 0}

    async def classify_then_fail(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return classifier_resp
        raise RuntimeError("Summarizer LLM failed")

    mock_create_message.side_effect = classify_then_fail

    from app.services.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(session)
    # Simulate having extraction data (page_images)
    orchestrator._last_extraction = MagicMock()
    orchestrator._last_extraction.page_images = []

    # Should NOT raise despite summarizer failure
    await orchestrator._classify_and_summarize(doc, trace_id="t1")

    # Classification results should be written to DB
    execute_calls = session.execute.call_args_list
    sql_texts = [str(c.args[0]) for c in execute_calls]
    assert any("SET doc_type" in s for s in sql_texts), (
        "Classification DB write should have occurred"
    )


@pytest.mark.asyncio
async def test_vectorize_failure_nonfatal(mock_create_message, mock_langfuse):
    """If vectorization throws in parallel, integration still succeeds."""
    doc = _make_doc()
    doc.status = "verified"
    session = _mock_session()

    # Mock fields for integration
    fields_result = MagicMock()
    fields_result.fetchall.return_value = []

    # Route different SQL queries
    def sql_router(*args, **kwargs):
        sql = str(args[0]) if args else ""
        if "field_name, field_value" in sql:
            return fields_result
        return MagicMock()

    session.execute = AsyncMock(side_effect=sql_router)

    # Integration agent response
    integrator_resp = _make_anthropic_response("IntegrationOutput", {
        "resolutions": [],
        "facts": [],
        "relationships": [],
    })
    mock_create_message.return_value = integrator_resp

    from app.services.pipeline.orchestrator import PipelineOrchestrator

    with (
        patch("app.services.pipeline.orchestrator.EntityResolver") as MockResolver,
        patch(
            "app.services.pipeline.orchestrator.vectorize_document",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Embeddings API down"),
        ),
        patch("app.services.pipeline.orchestrator.async_session_factory") as mock_factory,
    ):
        mock_vec_session = AsyncMock()
        mock_vec_session.__aenter__ = AsyncMock(return_value=mock_vec_session)
        mock_vec_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_vec_session

        mock_resolver = AsyncMock()
        mock_resolver.resolve_and_persist = AsyncMock()
        MockResolver.return_value = mock_resolver

        orchestrator = PipelineOrchestrator(session)
        orchestrator._last_extraction_output = MagicMock()
        orchestrator._last_extraction_output.detected_entities = []

        # Should NOT raise despite vectorizer failure
        await orchestrator._integrate_and_vectorize(doc, trace_id="t1")

        # Vectorization flag should NOT be set (will retry in vectorization stage)
        assert orchestrator._vectorization_done is False


@pytest.mark.asyncio
async def test_vectorization_stage_skipped_when_done(mock_create_message, mock_langfuse):
    """If vectorization completed in integration stage, vectorization stage is a no-op."""
    doc = _make_doc()
    doc.status = "integrated"
    session = _mock_session()

    from app.services.pipeline.orchestrator import PipelineOrchestrator

    with patch(
        "app.services.pipeline.orchestrator.vectorize_document",
        new_callable=AsyncMock,
    ) as mock_vectorize:
        orchestrator = PipelineOrchestrator(session)
        orchestrator._vectorization_done = True

        await orchestrator._run_stage(doc, "vectorization", trace_id="t1")

        # vectorize_document should NOT have been called
        mock_vectorize.assert_not_called()


@pytest.mark.asyncio
async def test_vectorization_stage_runs_when_not_done(mock_create_message, mock_langfuse):
    """If vectorization failed in integration stage, vectorization stage runs it."""
    doc = _make_doc()
    doc.status = "integrated"
    session = _mock_session()

    from app.services.pipeline.orchestrator import PipelineOrchestrator

    with patch(
        "app.services.pipeline.orchestrator.vectorize_document",
        new_callable=AsyncMock,
    ) as mock_vectorize:
        orchestrator = PipelineOrchestrator(session)
        orchestrator._vectorization_done = False

        await orchestrator._run_stage(doc, "vectorization", trace_id="t1")

        # vectorize_document SHOULD have been called
        mock_vectorize.assert_called_once()
