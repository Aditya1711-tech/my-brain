from fastapi import APIRouter
from sqlalchemy import text

from app.deps import DbSession

router = APIRouter()


@router.get("/health")
async def health(db: DbSession) -> dict[str, str]:
    """Health check — verifies DB connectivity."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
