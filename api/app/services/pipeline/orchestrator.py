"""Pipeline orchestrator — drives a document through all stages."""

import asyncio
import time
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.agents.classifier import ClassifierAgent, ClassifierInput
from app.agents.extractor import ExtractorAgent, ExtractorInput
from app.agents.schema_architect import SchemaArchitectAgent, SchemaArchitectInput
from app.agents.summarizer import SummarizerAgent, SummarizerInput
from app.agents.verifier import VerifierAgent, VerifierInput
from app.services.pipeline.groundedness import check_groundedness
from app.db.session import async_session_factory
from app.integrations.supabase_client import supabase
from app.parsing.router import parse_file
from app.repositories.documents_repo import DocumentsRepo
from app.repositories.events_repo import EventsRepo
from app.repositories.extracted_fields_repo import ExtractedFieldCreate, ExtractedFieldsRepo
from app.services.knowledge.entity_resolver import EntityResolver
from app.services.pipeline.state_machine import STATUS_TO_STAGE, can_transition, next_status_after
from app.services.pipeline.vectorizer import vectorize_document

logger = structlog.get_logger()


def _compute_retry_budget(confidence: float, importance: str) -> int:
    """Compute retry budget based on confidence and importance."""
    if confidence >= 0.85:
        return 0
    if confidence >= 0.6:
        return {"critical": 2, "important": 1, "nice_to_have": 0}.get(importance, 1)
    return {"critical": 3, "important": 2, "nice_to_have": 1}.get(importance, 2)


class PipelineOrchestrator:
    def __init__(self, db: AsyncSession) -> None:
        self.docs_repo = DocumentsRepo(db)
        self.events_repo = EventsRepo(db)
        self.db = db
        self._vectorization_done = False

    async def run(self, doc_id: UUID) -> None:
        """Drive a document through the pipeline until ready or failed."""
        doc = await self.docs_repo.get_by_id(doc_id)
        if doc is None:
            logger.error("pipeline.doc_not_found", doc_id=str(doc_id))
            return

        trace_id = str(doc_id)

        while doc.status not in ("ready", "failed"):
            stage = STATUS_TO_STAGE.get(doc.status)
            if stage is None:
                logger.info("pipeline.no_next_stage", doc_id=str(doc_id), status=doc.status)
                break

            next_stat = next_status_after(doc.status)
            if next_stat is None or not can_transition(doc.status, next_stat):
                logger.warning(
                    "pipeline.invalid_transition",
                    doc_id=str(doc_id),
                    current=doc.status,
                    target=next_stat,
                )
                break

            start = time.monotonic()
            try:
                await self._run_stage(doc, stage, trace_id)
                duration_ms = int((time.monotonic() - start) * 1000)

                await self.docs_repo.update_status(doc_id, next_stat)
                await self.events_repo.insert(
                    user_id=doc.user_id,
                    document_id=doc_id,
                    stage=stage,
                    status="success",
                    trace_id=trace_id,
                    duration_ms=duration_ms,
                )

                logger.info(
                    "pipeline.stage_complete",
                    doc_id=str(doc_id),
                    stage=stage,
                    new_status=next_stat,
                    duration_ms=duration_ms,
                )

                # Refresh doc status
                doc = await self.docs_repo.get_by_id(doc_id)
                if doc is None:
                    break

            except Exception as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.exception(
                    "pipeline.stage_failed",
                    doc_id=str(doc_id),
                    stage=stage,
                )
                await self.docs_repo.update_status(doc_id, "failed", failure_reason=str(exc))
                await self.events_repo.insert(
                    user_id=doc.user_id,
                    document_id=doc_id,
                    stage=stage,
                    status="failure",
                    details={"error": str(exc)},
                    trace_id=trace_id,
                    duration_ms=duration_ms,
                )
                break

    async def _run_stage(self, doc, stage: str, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Execute a single pipeline stage."""
        if stage == "text_extraction":
            await self._extract_text(doc, trace_id)
        elif stage == "classification":
            await self._classify_and_summarize(doc, trace_id)
        elif stage == "schema_building":
            await self._build_schema(doc, trace_id)
        elif stage == "extraction":
            await self._extract_fields(doc, trace_id)
        elif stage == "verification":
            await self._verify(doc, trace_id)
        elif stage == "integration":
            await self._integrate_and_vectorize(doc, trace_id)
        elif stage == "vectorization":
            if self._vectorization_done:
                logger.info("pipeline.vectorization_already_done", doc_id=str(doc.id))
            else:
                await self._vectorize(doc, trace_id)
        else:
            logger.info("pipeline.stage_stub", stage=stage, doc_id=str(doc.id))

    async def _extract_text(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Download file from Supabase storage and parse it."""
        logger.info("pipeline.extracting_text", doc_id=str(doc.id), storage_path=doc.storage_path)

        bucket = settings.supabase_storage_bucket
        file_bytes = supabase.storage.from_(bucket).download(doc.storage_path)

        extraction = parse_file(file_bytes, doc.mime_type, doc.original_filename)

        # Store raw text on document
        from sqlalchemy import text as sql_text

        await self.db.execute(
            sql_text("""
                UPDATE documents
                SET raw_text = :raw_text,
                    full_text_tsv = to_tsvector('english', COALESCE(:raw_text, '')),
                    updated_at = now()
                WHERE id = :doc_id
            """),
            {"raw_text": extraction.text, "doc_id": str(doc.id)},
        )
        await self.db.commit()

        # Store extraction data for next stages
        self._last_extraction = extraction

    async def _classify_and_summarize(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Run classification and summarization in parallel.

        Both agents only need raw_text, so we pre-read it once and
        run both LLM calls concurrently. DB writes are sequential.
        Summarize failure is non-fatal (logged, pipeline continues).
        """
        from sqlalchemy import text as sql_text

        # Pre-read shared data
        result = await self.db.execute(
            sql_text("SELECT raw_text FROM documents WHERE id = :doc_id"),
            {"doc_id": str(doc.id)},
        )
        row = result.fetchone()
        raw_text = row[0] or "" if row else ""  # type: ignore[index]

        extraction = getattr(self, "_last_extraction", None)
        page_image = None
        if extraction and extraction.page_images:
            page_image = extraction.page_images[0]

        # Run both LLM calls in parallel (no DB access during this phase)
        classify_coro = ClassifierAgent().run(
            ClassifierInput(
                text_sample=raw_text[:6000] if raw_text else "",
                has_image=page_image is not None,
            ),
            trace_id=trace_id,
            page_image=page_image,
        )
        summarize_coro = SummarizerAgent().run(
            SummarizerInput(
                document_type="document",
                text_sample=raw_text[:4000],
            ),
            trace_id=trace_id,
        )

        classify_output, summarize_output = await asyncio.gather(
            classify_coro, summarize_coro, return_exceptions=True,
        )

        # Classification failure is fatal
        if isinstance(classify_output, BaseException):
            raise classify_output

        # Write classification results to DB
        await self.db.execute(
            sql_text("""
                UPDATE documents
                SET doc_type = :doc_type,
                    domain = :domain,
                    country = :country,
                    language = :language,
                    is_scanned = :is_scanned,
                    is_handwritten = :is_handwritten,
                    updated_at = now()
                WHERE id = :doc_id
            """),
            {
                "doc_type": classify_output.document_type,
                "domain": classify_output.domain,
                "country": classify_output.country,
                "language": classify_output.primary_language,
                "is_scanned": classify_output.is_scanned,
                "is_handwritten": classify_output.is_handwritten,
                "doc_id": str(doc.id),
            },
        )
        await self.db.commit()

        # Summarize failure is non-fatal
        if isinstance(summarize_output, BaseException):
            logger.warning(
                "pipeline.summarize_failed_nonfatal",
                doc_id=str(doc.id),
                error=str(summarize_output),
            )
        elif summarize_output.summary:
            await self.db.execute(
                sql_text("""
                    UPDATE documents SET summary = :summary, updated_at = now()
                    WHERE id = :doc_id
                """),
                {"summary": summarize_output.summary[:500], "doc_id": str(doc.id)},
            )
            await self.db.commit()

    async def _build_schema(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Run schema architect agent."""
        from sqlalchemy import text as sql_text

        result = await self.db.execute(
            sql_text("SELECT raw_text, doc_type, domain FROM documents WHERE id = :doc_id"),
            {"doc_id": str(doc.id)},
        )
        row = result.fetchone()
        raw_text = row[0] or "" if row else ""  # type: ignore[index]
        doc_type = row[1] or "unknown" if row else "unknown"  # type: ignore[index]
        domain = row[2] or "other" if row else "other"  # type: ignore[index]

        input_data = SchemaArchitectInput(
            document_type=doc_type,
            domain=domain,
            text_sample=raw_text[:4000],
        )

        output = await SchemaArchitectAgent().run(input_data, trace_id=trace_id)

        # Persist schema on document
        import json

        await self.db.execute(
            sql_text("""
                UPDATE documents
                SET schema_json = CAST(:schema_json AS jsonb), updated_at = now()
                WHERE id = :doc_id
            """),
            {
                "schema_json": json.dumps(output.model_dump()),
                "doc_id": str(doc.id),
            },
        )
        await self.db.commit()

    async def _extract_fields(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Run extractor agent and persist extracted fields."""
        from sqlalchemy import text as sql_text
        import json

        # Load schema and text
        result = await self.db.execute(
            sql_text("SELECT raw_text, schema_json, doc_type FROM documents WHERE id = :doc_id"),
            {"doc_id": str(doc.id)},
        )
        row = result.fetchone()
        raw_text = row[0] or "" if row else ""  # type: ignore[index]
        schema_json = row[1] if row else None  # type: ignore[index]
        doc_type = row[2] or "unknown" if row else "unknown"  # type: ignore[index]

        schema_fields = []
        if schema_json:
            schema_data = schema_json if isinstance(schema_json, dict) else json.loads(schema_json)
            schema_fields = schema_data.get("fields", [])

        # Get page images
        extraction = getattr(self, "_last_extraction", None)
        page_images = extraction.page_images if extraction else []

        input_data = ExtractorInput(
            schema_fields=schema_fields,
            document_type=doc_type,
            text=raw_text[:8000],
            has_images=len(page_images) > 0,
        )

        output = await ExtractorAgent().run(
            input_data, trace_id=trace_id, page_images=page_images,
        )

        # Build field type lookup from schema
        field_type_map: dict[str, str] = {}
        field_entity_map: dict[str, bool] = {}
        for sf in schema_fields:
            field_type_map[sf["name"]] = sf.get("field_type", "string")
            field_entity_map[sf["name"]] = sf.get("is_entity_field", False)

        # Persist extracted fields
        fields_repo = ExtractedFieldsRepo(self.db)
        field_creates = [
            ExtractedFieldCreate(
                user_id=doc.user_id,
                document_id=doc.id,
                field_name=f.name,
                field_value=f.value,
                field_type=field_type_map.get(f.name, "string"),
                is_entity_ref=field_entity_map.get(f.name, False),
            )
            for f in output.fields
        ]
        await fields_repo.bulk_insert(field_creates)

        # Store extraction output for verifier
        self._last_extraction_output = output

    async def _verify(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Adaptive ground → verify → retry loop.

        1. Groundedness check (deterministic, fast)
        2. LLM verifier (on fields that aren't clearly ungrounded)
        3. Combine signals → per-field confidence + retry budget
        4. Retry extractor on fields with remaining budget
        5. Repeat until no retries needed or max iterations reached
        """
        from sqlalchemy import text as sql_text
        import json

        max_iterations = 4
        fields_repo = ExtractedFieldsRepo(self.db)

        # Load doc data
        result = await self.db.execute(
            sql_text("SELECT raw_text, schema_json, doc_type FROM documents WHERE id = :doc_id"),
            {"doc_id": str(doc.id)},
        )
        row = result.fetchone()
        raw_text = row[0] or "" if row else ""  # type: ignore[index]
        schema_json = row[1] if row else None  # type: ignore[index]
        doc_type = row[2] or "unknown" if row else "unknown"  # type: ignore[index]

        schema_fields: list[dict] = []
        if schema_json:
            schema_data = schema_json if isinstance(schema_json, dict) else json.loads(schema_json)
            schema_fields = schema_data.get("fields", [])

        # Build importance map from schema
        importance_map = {
            sf["name"]: sf.get("importance", "important") for sf in schema_fields
        }

        # Track per-field retry budgets across iterations
        budgets: dict[str, int] = {}  # field_name → remaining budget

        extraction = getattr(self, "_last_extraction", None)
        page_images = extraction.page_images if extraction else []

        for iteration in range(1, max_iterations + 1):
            # Get current extracted fields
            extracted = await fields_repo.get_by_document(doc.id)
            field_dicts = [
                {"name": f["field_name"], "value": f["field_value"], "type": f["field_type"]}
                for f in extracted
            ]

            # 1. Groundedness check
            ground_results = check_groundedness(field_dicts, raw_text, schema_fields)

            # 2. LLM verifier
            verifier_input = VerifierInput(
                document_type=doc_type,
                schema_fields=schema_fields,
                extracted_fields=field_dicts,
                text_sample=raw_text[:16000],
            )
            verification = await VerifierAgent().run(verifier_input, trace_id=trace_id)

            # 3. Combine signals and persist
            verify_map = {fv.field_name: fv for fv in verification.fields}
            to_retry: list[str] = []

            for fd in field_dicts:
                name = fd["name"]
                g = ground_results.get(name)
                v = verify_map.get(name)
                importance = importance_map.get(name, "important")

                # Compute final confidence
                confidence = v.confidence if v else 0.5
                if g and not g.is_grounded and not g.is_ambiguous:
                    confidence = min(confidence, 0.3)
                elif g and g.is_ambiguous:
                    confidence = confidence * 0.9

                needs_retry = v.needs_retry if v else False

                # Compute retry budget on first iteration
                if name not in budgets:
                    budgets[name] = _compute_retry_budget(confidence, importance)
                    if g and not g.is_grounded and not g.is_ambiguous:
                        budgets[name] = min(budgets[name] + 1, 3)

                reasoning_parts = []
                if v:
                    reasoning_parts.append(v.reasoning)
                if g and not g.is_grounded:
                    reasoning_parts.append(f"not grounded ({g.method})")
                reasoning = "; ".join(reasoning_parts) or "no verification data"

                # Persist verification state
                await fields_repo.update_verification(
                    document_id=doc.id,
                    field_name=name,
                    confidence=confidence,
                    needs_retry=needs_retry and budgets[name] > 0,
                    reasoning=reasoning,
                    is_grounded=g.is_grounded if g else None,
                    groundedness_method=g.method if g else None,
                    importance=importance,
                    retry_budget=budgets.get(name, 0) + (
                        _compute_retry_budget(confidence, importance)
                        if name not in budgets else 0
                    ),
                    retry_budget_remaining=budgets[name],
                )

                # Decide if this field needs retry
                if budgets[name] > 0 and (needs_retry or (g and not g.is_grounded)):
                    to_retry.append(name)

            # 4. If nothing to retry, we're done
            if not to_retry:
                logger.info(
                    "pipeline.verify_complete",
                    doc_id=str(doc.id),
                    iteration=iteration,
                )
                break

            # 5. Retry extractor on flagged fields
            logger.info(
                "pipeline.retry_extraction",
                doc_id=str(doc.id),
                iteration=iteration,
                retry_fields=to_retry,
            )

            feedback_parts = []
            for name in to_retry:
                g = ground_results.get(name)
                v = verify_map.get(name)
                parts = []
                if g and not g.is_grounded:
                    field_val = next(
                        (fd["value"] for fd in field_dicts if fd["name"] == name), None,
                    )
                    parts.append(f"value '{field_val}' not found in source")
                if v and v.reasoning:
                    parts.append(v.reasoning)
                feedback_parts.append(f"{name}: {'; '.join(parts)}")

            retry_input = ExtractorInput(
                schema_fields=schema_fields,
                document_type=doc_type,
                text=raw_text[:8000],
                has_images=len(page_images) > 0,
                retry_fields=to_retry,
                retry_feedback="; ".join(feedback_parts),
            )

            retry_output = await ExtractorAgent().run(
                retry_input, trace_id=trace_id, page_images=page_images,
            )

            # 6. Update retried fields and decrement budgets
            for f in retry_output.fields:
                if f.name in to_retry:
                    await self.db.execute(
                        sql_text("""
                            UPDATE extracted_fields
                            SET field_value = :value,
                                needs_retry = false,
                                retry_count = retry_count + 1
                            WHERE document_id = :doc_id AND field_name = :field_name
                        """),
                        {
                            "value": f.value,
                            "doc_id": str(doc.id),
                            "field_name": f.name,
                        },
                    )
            await self.db.commit()

            # Decrement budgets for retried fields
            for name in to_retry:
                budgets[name] = max(0, budgets[name] - 1)

    async def _integrate(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Run knowledge integration — entity resolution, facts, relationships."""
        from sqlalchemy import text as sql_text
        import json

        fields_repo = ExtractedFieldsRepo(self.db)

        # Load doc data
        result = await self.db.execute(
            sql_text("SELECT raw_text, schema_json, doc_type FROM documents WHERE id = :doc_id"),
            {"doc_id": str(doc.id)},
        )
        row = result.fetchone()
        doc_type = row[2] or "unknown" if row else "unknown"  # type: ignore[index]

        # Get extracted fields
        extracted = await fields_repo.get_by_document(doc.id)
        extracted_dicts = [
            {"name": f["field_name"], "value": f["field_value"], "type": f["field_type"]}
            for f in extracted
        ]

        # Build detected entities from extractor output or from entity-ref fields
        extraction_output = getattr(self, "_last_extraction_output", None)
        detected_entities: list[dict] = []

        if extraction_output and extraction_output.detected_entities:
            detected_entities = [e.model_dump() for e in extraction_output.detected_entities]
        else:
            # Fallback: build entities from fields marked as entity refs
            entity_fields = [f for f in extracted if f.get("is_entity_ref") and f["field_value"]]
            seen_names: set[str] = set()
            for ef in entity_fields:
                name = ef["field_value"]
                if name not in seen_names:
                    seen_names.add(name)
                    detected_entities.append({
                        "name": name,
                        "type": "person",
                        "role": "subject",
                        "fields": {},
                    })

        if not detected_entities:
            logger.info("pipeline.integration_skip_no_entities", doc_id=str(doc.id))
            return

        # Run entity resolution + persist
        resolver = EntityResolver(self.db)
        await resolver.resolve_and_persist(
            user_id=doc.user_id,
            document_id=doc.id,
            document_type=doc_type,
            detected_entities=detected_entities,
            extracted_fields=extracted_dicts,
            trace_id=trace_id,
        )

    async def _integrate_and_vectorize(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Run integration and vectorization in parallel.

        Uses a separate DB session for vectorization to avoid
        concurrent access on the orchestrator's AsyncSession.
        Integration failure is fatal; vectorize failure is non-fatal
        (retried in the subsequent vectorization stage).
        """

        async def _vectorize_parallel() -> None:
            async with async_session_factory() as vec_db:
                await vectorize_document(vec_db, doc.id, doc.user_id, trace_id=trace_id)

        integrate_result, vectorize_result = await asyncio.gather(
            self._integrate(doc, trace_id),
            _vectorize_parallel(),
            return_exceptions=True,
        )

        # Integration failure is fatal
        if isinstance(integrate_result, BaseException):
            raise integrate_result

        # Vectorize failure is non-fatal; will retry in vectorization stage
        if isinstance(vectorize_result, BaseException):
            logger.warning(
                "pipeline.vectorize_parallel_failed",
                doc_id=str(doc.id),
                error=str(vectorize_result),
            )
        else:
            self._vectorization_done = True

    async def _vectorize(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Chunk text and generate embeddings."""
        await vectorize_document(self.db, doc.id, doc.user_id, trace_id=trace_id)
