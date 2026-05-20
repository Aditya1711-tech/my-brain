from langfuse import Langfuse

from app.config import settings

langfuse = Langfuse(
    public_key=settings.langfuse_public_key or None,
    secret_key=settings.langfuse_secret_key or None,
    host=settings.langfuse_host or None,
    enabled=bool(settings.langfuse_public_key and settings.langfuse_secret_key),
)
