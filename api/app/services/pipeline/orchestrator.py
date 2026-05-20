"""Pipeline orchestrator — drives a document through all stages."""

import time
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.classifier import ClassifierInput, classifier_agent
from app.integrations.supabase_client import supabase
from app.parsing.router import parse_file
from app.repositories.documents_repo import DocumentsRepo
from app.repositories.events_repo import EventsRepo
from app.services.pipeline.state_machine import STATUS_TO_STAGE, can_transition, next_status_after

logger = structlog.get_logger()


class PipelineOrchestrator:
    def __init__(self, db: AsyncSession) -> None:
        self.docs_repo = DocumentsRepo(db)
        self.events_repo = EventsRepo(db)
        self.db = db

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
            await self._classify(doc, trace_id)
        else:
            # Stages D3+ (schema_building, extraction, verification, integration, vectorization)
            # will be wired in Day 3
            logger.info("pipeline.stage_stub", stage=stage, doc_id=str(doc.id))

    async def _extract_text(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Download file from Supabase storage and parse it."""
        logger.info("pipeline.extracting_text", doc_id=str(doc.id), storage_path=doc.storage_path)

        file_bytes = supabase.storage.from_(
            doc.storage_path.split("/")[0]
            if "/" in doc.storage_path
            else "user-uploads"
        ).download(
            "/".join(doc.storage_path.split("/")[1:])
            if "/" in doc.storage_path
            else doc.storage_path
        )

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

    async def _classify(self, doc, trace_id: str) -> None:  # type: ignore[no-untyped-def]
        """Run classifier agent on the extracted text."""
        from sqlalchemy import text as sql_text

        # Get the raw text
        result = await self.db.execute(
            sql_text("SELECT raw_text FROM documents WHERE id = :doc_id"),
            {"doc_id": str(doc.id)},
        )
        row = result.fetchone()
        raw_text = row[0] if row else ""  # type: ignore[index]

        # Get page images if available
        extraction = getattr(self, "_last_extraction", None)
        page_image = None
        if extraction and extraction.page_images:
            page_image = extraction.page_images[0]

        input_data = ClassifierInput(
            text_sample=raw_text[:6000] if raw_text else "",
            has_image=page_image is not None,
        )

        if page_image:
            classifier_agent.set_page_image(page_image)

        output = await classifier_agent.run(input_data, trace_id=trace_id)

        # Update document with classification results
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
                "doc_type": output.document_type,
                "domain": output.domain,
                "country": output.country,
                "language": output.primary_language,
                "is_scanned": output.is_scanned,
                "is_handwritten": output.is_handwritten,
                "doc_id": str(doc.id),
            },
        )
        await self.db.commit()
