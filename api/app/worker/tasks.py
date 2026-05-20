from uuid import UUID

import structlog

from app.db.session import async_session_factory
from app.services.pipeline.orchestrator import PipelineOrchestrator

logger = structlog.get_logger()


async def process_document(ctx: dict, doc_id: str) -> str:  # type: ignore[type-arg]
    """Process a document through the full pipeline."""
    logger.info("process_document.start", doc_id=doc_id)

    async with async_session_factory() as session:
        orchestrator = PipelineOrchestrator(session)
        await orchestrator.run(UUID(doc_id))

    logger.info("process_document.done", doc_id=doc_id)
    return f"Document {doc_id} processed"
