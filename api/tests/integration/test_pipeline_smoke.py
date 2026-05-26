"""Smoke tests: pipeline with mocked LLMs.

Tests:
1. Happy path — one document through all stages (grounded values, no retries)
2. Adaptive retry — hallucinated field triggers groundedness-driven retry loop

Does NOT require a running database or external services.
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
            FAKE_RAW_TEXT,
            SCHEMA_JSON,
            "passport",
        )
    if "raw_text, doc_type, domain" in sql:
        # _build_schema SELECT
        return _make_result(
            FAKE_RAW_TEXT,
            "passport",
            "personal",
        )
    if "raw_text FROM" in sql:
        # _classify SELECT
        return _make_result(FAKE_RAW_TEXT)
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
        parse_result.text = FAKE_RAW_TEXT
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


@pytest.mark.asyncio
async def test_verify_retries_ungrounded_field(
    mock_create_message,
    mock_langfuse,
    canned_pipeline_responses,
):
    """A hallucinated passport_number triggers groundedness-driven retry.

    Setup: extracted passport_number is 'X9999999' which is NOT in the
    source text. Groundedness check marks it ungrounded → retry fires.
    The retry extractor returns the correct value 'A1234567'.
    """

    doc = _make_doc_row()
    doc_id = doc.id

    async def fake_update_status(did, new_status, **kwargs):
        doc.status = new_status

    async def fake_get_by_id(did):
        return doc

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_sql_router)
    mock_session.commit = AsyncMock()

    # Verifier says passport_number needs retry (low confidence)
    verifier_with_retry = _make_anthropic_response("VerificationOutput", {
        "fields": [
            {
                "field_name": "full_name",
                "confidence": 0.95,
                "needs_retry": False,
                "importance": "critical",
                "retry_budget": 0,
                "reasoning": "Matches text",
            },
            {
                "field_name": "passport_number",
                "confidence": 0.4,
                "needs_retry": True,
                "importance": "critical",
                "retry_budget": 3,
                "reasoning": "Value not found in document",
            },
        ],
        "overall_quality": 0.6,
    })

    # After retry, verifier accepts both fields
    verifier_after_retry = _make_anthropic_response("VerificationOutput", {
        "fields": [
            {
                "field_name": "full_name",
                "confidence": 0.95,
                "needs_retry": False,
                "importance": "critical",
                "retry_budget": 0,
                "reasoning": "Matches text",
            },
            {
                "field_name": "passport_number",
                "confidence": 0.98,
                "needs_retry": False,
                "importance": "critical",
                "retry_budget": 0,
                "reasoning": "Now matches document",
            },
        ],
        "overall_quality": 0.96,
    })

    # Retry extractor returns correct value
    retry_extractor = _make_anthropic_response("ExtractionOutput", {
        "fields": [
            {"name": "passport_number", "value": "A1234567"},
        ],
        "detected_entities": [],
    })

    # Pipeline order: classifier, schema_architect, extractor,
    # verifier (retry), retry_extractor, verifier (accept), integrator
    responses = [
        canned_pipeline_responses[0],  # classifier
        canned_pipeline_responses[1],  # schema_architect
        canned_pipeline_responses[2],  # extractor
        verifier_with_retry,           # first verify → triggers retry
        retry_extractor,               # retry extractor
        verifier_after_retry,          # second verify → accepts
        canned_pipeline_responses[4],  # knowledge integrator
    ]
    mock_create_message.side_effect = responses

    # Track which field values the retry UPDATE receives
    retry_values: list[dict] = []
    original_router = _sql_router

    def tracking_sql_router(*args, **kwargs):
        sql = str(args[0]) if len(args) > 0 else ""
        if "SET field_value" in sql and len(args) > 1:
            params = args[1]
            if isinstance(params, dict):
                retry_values.append(dict(params))
        return original_router(*args, **kwargs)

    mock_session.execute = AsyncMock(side_effect=tracking_sql_router)

    with (
        patch("app.services.pipeline.orchestrator.supabase") as mock_supabase,
        patch("app.services.pipeline.orchestrator.parse_file") as mock_parse,
        patch("app.services.pipeline.orchestrator.vectorize_document", new_callable=AsyncMock),
        patch("app.services.pipeline.orchestrator.EntityResolver") as MockResolver,
    ):
        mock_bucket = MagicMock()
        mock_bucket.download.return_value = b"fake pdf bytes"
        mock_supabase.storage.from_.return_value = mock_bucket

        parse_result = MagicMock()
        parse_result.text = FAKE_RAW_TEXT
        parse_result.page_images = [b"fake_page_image"]
        mock_parse.return_value = parse_result

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

            # First call returns hallucinated passport_number;
            # after retry updates the DB, subsequent calls return corrected value.
            call_count = {"n": 0}

            async def evolving_get_by_document(doc_id):
                call_count["n"] += 1
                passport_value = "X9999999" if call_count["n"] <= 1 else "A1234567"
                return [
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
                    {
                        "id": str(uuid4()),
                        "field_name": "passport_number",
                        "field_value": passport_value,
                        "field_type": "identifier",
                        "confidence": None,
                        "needs_retry": False,
                        "retry_count": 0 if call_count["n"] <= 1 else 1,
                        "reasoning": None,
                        "is_entity_ref": False,
                    },
                ]

            mock_fields_repo.get_by_document = AsyncMock(
                side_effect=evolving_get_by_document,
            )
            mock_fields_repo.update_verification = AsyncMock()
            MockFieldsRepo.return_value = mock_fields_repo

            await orchestrator.run(doc_id)

    # Pipeline should complete successfully
    assert doc.status == "vectorized", f"Expected vectorized, got {doc.status}"

    # update_verification should have been called for passport_number
    # with is_grounded=False on first iteration
    verify_calls = mock_fields_repo.update_verification.call_args_list
    passport_calls = [
        c for c in verify_calls
        if c.kwargs.get("field_name") == "passport_number"
    ]
    assert len(passport_calls) >= 2, (
        f"Expected at least 2 verification updates for passport_number "
        f"(initial + after retry), got {len(passport_calls)}"
    )
    # First call should mark as ungrounded
    assert passport_calls[0].kwargs["is_grounded"] is False, (
        "First verification should mark passport_number as ungrounded"
    )
