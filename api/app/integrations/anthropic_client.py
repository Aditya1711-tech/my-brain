import anthropic

from app.config import settings
from app.utils.retry import retry_on_transient

client = anthropic.AsyncAnthropic(
    api_key=settings.anthropic_api_key.get_secret_value(),
)


async def create_message(**kwargs: object) -> anthropic.types.Message:
    """Call messages.create with retry on transient errors (429/5xx)."""
    return await retry_on_transient(client.messages.create, **kwargs)
