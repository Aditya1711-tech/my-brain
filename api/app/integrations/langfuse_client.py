from langfuse import Langfuse

from app.config import settings

_has_keys = bool(settings.langfuse_public_key and settings.langfuse_secret_key)

if _has_keys:
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host or None,
    )
    langfuse.enabled = True  # type: ignore[attr-defined]
else:
    langfuse = Langfuse()
    langfuse.enabled = False  # type: ignore[attr-defined]
