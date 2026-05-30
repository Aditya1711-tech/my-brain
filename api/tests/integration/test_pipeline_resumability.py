"""Tests for pipeline crash resumability (D-PIPELINE-01).

Verifies:
1. Page images are uploaded to Supabase Storage during text extraction
2. processing_state is persisted after each stage
3. Pipeline resumes from the last successful stage after a crash
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import _make_anthropic_response

FAKE_RAW_TEXT = (
    "REPUBLIC OF INDIA\nPASSPORT\n"
    "Name: John Doe\nPassport No: A1234567\n"
    "Date of Birth: 15/01/1990\nNationality: INDIAN"
)

SCHEMA_JSON = {
    "document_type": "passport",
    "fields": [
        {
            "name": "full_name",
            "field_type": "string",
            "description": "Name",
            "required": True,
            "is_entity_field": True,
            "importance": "critical",
        },
    ],
}


def _make_doc_row(**overrides):
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "status": "uploaded",
        "storage_path": "user-uploads/test.pdf",
        "mime_type": "application/pdf",
        "original_filename": "test.pdf",
    }
    defaults.update(overrides)
    doc = MagicMock()
    for k, v in defaults.items():
        setattr(doc, k, v)
    return doc


def _make_result(*values):
    row = MagicMock()
    row.__getitem__ = lambda self, idx: values[idx]
    result = MagicMock()
    result.fetchone.return_value = row
    return result


@pytest.mark.asyncio
async def test_page_images_uploaded_to_storage(mock_create_message, mock_langfuse):
    """Text extraction uploads page images to Supabase Storage."""
    doc = _make_doc_row()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()

    with (
        patch("app.services.pipeline.orchestrator.supabase") as mock_supabase,
        patch("app.services.pipeline.orchestrator.parse_file") as mock_parse,
    ):
        mock_bucket = MagicMock()
        mock_bucket.download.return_value = b"fake pdf bytes"
        mock_supabase.storage.from_.return_value = mock_bucket

        parse_result = MagicMock()
        parse_result.text = FAKE_RAW_TEXT
        parse_result.page_images = [b"page_img_0", b"page_img_1"]
        mock_parse.return_value = parse_result

        from app.services.pipeline.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(mock_session)
        await orchestrator._extract_text(doc, trace_id="t1")

    # Verify upload called for each page image
    assert mock_bucket.upload.call_count == 2
    call_paths = [c.args[0] for c in mock_bucket.upload.call_args_list]
    assert f"page-images/{doc.id}/page_0.png" in call_paths
    assert f"page-images/{doc.id}/page_1.png" in call_paths

    # Verify paths stored on orchestrator
    assert len(orchestrator._page_image_paths) == 2


@pytest.mark.asyncio
async def test_processing_state_persisted(mock_create_message, mock_langfuse):
    """_save_processing_state writes page_image_paths and vectorization_done."""
    doc = _make_doc_row()

    sql_calls: list[tuple] = []
    mock_session = AsyncMock()

    async def tracking_execute(*args, **kwargs):
        sql_calls.append(args)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=tracking_execute)
    mock_session.commit = AsyncMock()

    from app.services.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(mock_session)
    orchestrator._page_image_paths = ["page-images/abc/page_0.png"]
    orchestrator._vectorization_done = True

    await orchestrator._save_processing_state(doc.id)

    # Find the processing_state UPDATE
    state_writes = [
        c for c in sql_calls
        if "processing_state" in str(c[0])
    ]
    assert len(state_writes) == 1, "Should write processing_state once"

    # Verify the JSON payload
    params = state_writes[0][1]
    state = json.loads(params["state"])
    assert state["page_image_paths"] == ["page-images/abc/page_0.png"]
    assert state["vectorization_done"] is True


@pytest.mark.asyncio
async def test_load_processing_state_restores_page_images(
    mock_create_message, mock_langfuse,
):
    """_load_processing_state downloads page images and hydrates _last_extraction."""
    doc = _make_doc_row()
    saved_state = json.dumps({
        "page_image_paths": [f"page-images/{doc.id}/page_0.png"],
        "vectorization_done": False,
    })

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_make_result(saved_state))
    mock_session.commit = AsyncMock()

    with patch("app.services.pipeline.orchestrator.supabase") as mock_supabase:
        mock_bucket = MagicMock()
        mock_bucket.download.return_value = b"restored_page_img"
        mock_supabase.storage.from_.return_value = mock_bucket

        from app.services.pipeline.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(mock_session)
        await orchestrator._load_processing_state(doc.id)

    # Page images should be restored
    assert orchestrator._page_image_paths == [f"page-images/{doc.id}/page_0.png"]
    assert hasattr(orchestrator, "_last_extraction")
    assert orchestrator._last_extraction.page_images == [b"restored_page_img"]
    assert orchestrator._vectorization_done is False


@pytest.mark.asyncio
async def test_load_processing_state_restores_vectorization_flag(
    mock_create_message, mock_langfuse,
):
    """_load_processing_state restores _vectorization_done flag."""
    saved_state = json.dumps({
        "page_image_paths": [],
        "vectorization_done": True,
    })

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_make_result(saved_state))
    mock_session.commit = AsyncMock()

    from app.services.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(mock_session)
    await orchestrator._load_processing_state(uuid4())

    assert orchestrator._vectorization_done is True


def _resume_sql_router(doc_id, saved_state_json):
    """Build a SQL router that returns processing_state for resume tests."""

    def router(*args, **kwargs):
        sql = str(args[0]) if args else ""
        if "processing_state FROM" in sql:
            return _make_result(saved_state_json)
        if "raw_text, schema_json, doc_type" in sql:
            return _make_result(FAKE_RAW_TEXT, SCHEMA_JSON, "passport")
        if "raw_text, doc_type, domain" in sql:
            return _make_result(FAKE_RAW_TEXT, "passport", "personal")
        if "raw_text FROM" in sql:
            return _make_result(FAKE_RAW_TEXT)
        if "raw_text, summary FROM" in sql:
            return _make_result(FAKE_RAW_TEXT, "A passport for John Doe.")
        if "field_name, field_value FROM" in sql:
            result = MagicMock()
            result.fetchall.return_value = [("full_name", "John Doe")]
            return result
        return MagicMock()

    return router


@pytest.mark.asyncio
async def test_pipeline_resumes_from_midpoint(
    mock_create_message, mock_langfuse, canned_pipeline_responses,
):
    """After a crash at schema_built, pipeline resumes from extraction."""
    doc = _make_doc_row(status="schema_built")
    doc_id = doc.id
    transitions: list[str] = [doc.status]

    saved_state = json.dumps({
        "page_image_paths": [f"page-images/{doc.id}/page_0.png"],
        "vectorization_done": False,
    })

    async def fake_update_status(did, new_status, **kwargs):
        doc.status = new_status
        transitions.append(new_status)

    async def fake_get_by_id(did):
        return doc

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=_resume_sql_router(doc_id, saved_state),
    )
    mock_session.commit = AsyncMock()

    # Only need LLM responses from extraction onwards:
    # [3]=extractor, [4]=verifier, [5]=knowledge_integrator
    mock_create_message.side_effect = [
        canned_pipeline_responses[3],  # extractor
        canned_pipeline_responses[4],  # verifier
        canned_pipeline_responses[5],  # knowledge integrator
    ]

    with (
        patch("app.services.pipeline.orchestrator.supabase") as mock_supabase,
        patch("app.services.pipeline.orchestrator.vectorize_document", new_callable=AsyncMock),
        patch("app.services.pipeline.orchestrator.EntityResolver") as MockResolver,
        patch("app.services.pipeline.orchestrator.async_session_factory") as mock_factory,
    ):
        mock_bucket = MagicMock()
        mock_bucket.download.return_value = b"restored_page_image"
        mock_supabase.storage.from_.return_value = mock_bucket

        mock_vec_session = AsyncMock()
        mock_vec_session.__aenter__ = AsyncMock(return_value=mock_vec_session)
        mock_vec_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_vec_session

        mock_resolver_instance = AsyncMock()
        mock_resolver_instance.resolve_and_persist = AsyncMock()
        MockResolver.return_value = mock_resolver_instance

        from app.repositories.documents_repo import DocumentsRepo
        from app.repositories.events_repo import EventsRepo
        from app.repositories.extracted_fields_repo import ExtractedFieldsRepo
        from app.services.pipeline.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(mock_session)
        orchestrator.docs_repo = MagicMock(spec=DocumentsRepo)
        orchestrator.docs_repo.get_by_id = AsyncMock(side_effect=fake_get_by_id)
        orchestrator.docs_repo.update_status = AsyncMock(side_effect=fake_update_status)
        orchestrator.events_repo = MagicMock(spec=EventsRepo)
        orchestrator.events_repo.insert = AsyncMock()

        with patch(
            "app.services.pipeline.orchestrator.ExtractedFieldsRepo"
        ) as MockFieldsRepo:
            mock_fields_repo = MagicMock(spec=ExtractedFieldsRepo)
            mock_fields_repo.bulk_insert = AsyncMock()
            mock_fields_repo.get_by_document = AsyncMock(return_value=[
                {
                    "id": str(uuid4()),
                    "field_name": "full_name",
                    "field_value": "John Doe",
                    "field_type": "string",
                    "confidence": None,
                    "needs_retry": False,
                    "retry_count": 0,
                    "reasoning": None,
                    "is_entity_ref": True,
                },
            ])
            mock_fields_repo.update_verification = AsyncMock()
            MockFieldsRepo.return_value = mock_fields_repo

            await orchestrator.run(doc_id)

    # Pipeline should resume from schema_built (not restart from uploaded)
    expected_flow = [
        "schema_built",  # starting status
        "extracted",      # after extraction
        "verified",       # after verification
        "integrated",     # after integration
        "vectorized",     # after vectorization
    ]
    assert transitions == expected_flow, (
        f"Expected resume flow {expected_flow}, got {transitions}"
    )

    # Page images should have been restored from Storage
    mock_bucket.download.assert_any_call(f"page-images/{doc.id}/page_0.png")
