from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db

# Re-export for convenience
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def verify_api_key(
    x_api_key: Annotated[str, Header()],
) -> str:
    """Verify the shared secret between Next.js BFF and FastAPI."""
    if x_api_key != settings.backend_api_key.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


VerifiedApiKey = Annotated[str, Depends(verify_api_key)]
