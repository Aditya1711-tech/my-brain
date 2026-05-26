"""Smoke test: one document through the full pipeline with mocked LLMs.

Validates the orchestrator state-machine flow by mocking:
- Database (AsyncSession) — tracks status transitions
- Supabase storage — returns fake file bytes
- LLM clients — return canned agent responses
- Vectorizer — skips real embedding generation

Does NOT require a running database or external services.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

SCHEMA_JSON = {
    "document_type": "passport",
    "fields": [
        {
            "name": "full_name",
            "field_type": "string",
            "description": "Name",
            "required": True,
            "is_entity_field": True,
        },
    ],
}


def _make_doc_row(**overrides):
    """Build a fake document row object with attribute access."""
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
    """Build a fake DB result whose fetchone() returns a tuple-like row."""
    row = MagicMock()
    row.__getitem__ = lambda self, idx: values[idx]
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _sql_router(*_args, **_kwargs):
    """Route mock DB execute() calls by inspecting the SQL text."""
    sql = str(_args[0]) if len(_args) > 0 else ""

    if "SET raw_text" in sql:
        # _extract_text UPDATE — no result needed
        return MagicMock()
    if "SET doc_type" in sql:
        # _classify UPDATE
        return MagicMock()
    if "SET schema_json" in sql:
        # _build_schema UPDATE
        return MagicMock()
    if "SET summary" in sql:
        # _extract_fields UPDATE summary
        return MagicMock()
    if "SET field_value" in sql:
        # _verify retry UPDATE
        return MagicMock()
    if "raw_text, schema_json, doc_type" in sql:
        # _extract_fields or _verify SELECT
        return _make_result(
            "Sample document text for testing",
            SCHEMA_JSON,
            "passport",
        )
    if "raw_text, doc_type, domain" in sql:
        # _build_schema SELECT
        return _make_result(
            "Sample document text for testing",
            "passport",
            "personal",
        )
    if "raw_text FROM" in sql:
        # _classify SELECT
        return _make_result("Sample document text for testing")
    # Fallback
    return MagicMock()


@pytest.mark.asyncio
async def test_pipeline_completes_all_stages(
    mock_create_message,
    mock_langfuse,
    canned_pipeline_responses,
):
    """A document should transition through all stages to 'vectorized'
    when every agent returns valid canned output."""

    doc = _make_doc_row()
    doc_id = doc.id
    transitions: list[str] = [doc.status]

    async def fake_update_status(did, new_status, **kwargs):
        doc.status = new_status
        transitions.append(new_status)

    async def fake_get_by_id(did):
        return doc

    # Mock DB session with SQL-aware routing
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_sql_router)
    mock_session.commit = AsyncMock()

    # Set up canned LLM responses in pipeline order
    mock_create_message.side_effect = canned_pipeline_responses

    with (
        patch("app.services.pipeline.orchestrator.supabase") as mock_supabase,
        patch("app.services.pipeline.orchestrator.parse_file") as mock_parse,
        patch("app.services.pipeline.orchestrator.vectorize_document", new_callable=AsyncMock),
        patch("app.services.pipeline.orchestrator.EntityResolver") as MockResolver,
    ):
        # Mock file download + parsing
        mock_bucket = MagicMock()
        mock_bucket.download.return_value = b"fake pdf bytes"
        mock_supabase.storage.from_.return_value = mock_bucket

        parse_result = MagicMock()
        parse_result.text = "Sample document text for testing"
        parse_result.page_images = [b"fake_page_image"]
        mock_parse.return_value = parse_result

        # Mock entity resolver
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

    expected_flow = [
        "uploaded",
        "extracting_text",
        "classified",
        "schema_built",
        "extracted",
        "verified",
        "integrated",
        "vectorized",
    ]
    assert transitions == expected_flow, (
        f"Expected status flow {expected_flow}, got {transitions}"
    )

    # Every stage should have recorded a success event
    assert orchestrator.events_repo.insert.call_count == 7, (
        f"Expected 7 pipeline events, got {orchestrator.events_repo.insert.call_count}"
    )
    for call in orchestrator.events_repo.insert.call_args_list:
        assert call.kwargs.get("status") == "success", (
            f"Stage {call.kwargs.get('stage')} did not report success"
        )
