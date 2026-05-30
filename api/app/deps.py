from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db

# Re-export for convenience
DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Inter-service auth (BFF → backend, e.g. /enqueue)
# ---------------------------------------------------------------------------

async def verify_api_key(
    x_api_key: Annotated[str, Header()],
) -> str:
    """Verify the shared secret between Next.js BFF and FastAPI."""
    if x_api_key != settings.backend_api_key.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


VerifiedApiKey = Annotated[str, Depends(verify_api_key)]


# ---------------------------------------------------------------------------
# User-facing JWT auth (Supabase access_token on /search /chat /threads)
# ---------------------------------------------------------------------------

async def verify_jwt(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    """Verify Supabase JWT from Authorization header and return user_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience="authenticated",
        )
        return UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


VerifiedUser = Annotated[UUID, Depends(verify_jwt)]
