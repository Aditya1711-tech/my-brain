from uuid import UUID

import structlog
from arq.connections import ArqRedis, create_pool
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.deps import DbSession, VerifiedApiKey
from app.repositories.documents_repo import DocumentsRepo
from app.worker.worker import parse_redis_url

logger = structlog.get_logger()
router = APIRouter()

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(parse_redis_url(settings.redis_url))
    return _arq_pool


@router.post("/enqueue")
async def enqueue_document(
    doc_id: UUID,
    _api_key: VerifiedApiKey,
    db: DbSession,
) -> dict[str, str]:
    """Enqueue a document for processing. Called by the Next.js BFF."""
    repo = DocumentsRepo(db)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pool = await get_arq_pool()
    job = await pool.enqueue_job("process_document", str(doc_id))
    logger.info("document_enqueued", doc_id=str(doc_id), job_id=job.job_id)
    return {"job_id": job.job_id}
