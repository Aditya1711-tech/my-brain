import structlog
from arq.jobs import Job
from sqlalchemy import text

from app.db.session import async_session_factory

logger = structlog.get_logger()


async def process_document_dummy(ctx: dict, doc_id: str) -> str:  # type: ignore[type-arg]
    """Dummy task — logs receipt and updates document status.

    Will be replaced by the real pipeline orchestrator in D2-BE-04.
    """
    logger.info("process_document_dummy.start", doc_id=doc_id)

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id, status FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        row = result.fetchone()

        if row is None:
            logger.warning("process_document_dummy.not_found", doc_id=doc_id)
            return f"Document {doc_id} not found"

        await session.execute(
            text(
                "UPDATE documents SET status = 'extracting_text', updated_at = now() "
                "WHERE id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
        await session.commit()

    logger.info("process_document_dummy.done", doc_id=doc_id, new_status="extracting_text")
    return f"Document {doc_id} status updated to extracting_text"
