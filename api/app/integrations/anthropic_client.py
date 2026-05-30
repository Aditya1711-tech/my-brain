import asyncio

import anthropic

from app.config import settings
from app.utils.retry import retry_on_transient

client = anthropic.AsyncAnthropic(
    api_key=settings.anthropic_api_key.get_secret_value(),
)

# Process-level concurrency cap — protects against rate-limit storms
_semaphore = asyncio.Semaphore(10)


async def create_message(**kwargs: object) -> anthropic.types.Message:
    """Call messages.create with concurrency cap + retry on transient errors."""
    async with _semaphore:
        return await retry_on_transient(client.messages.create, **kwargs)
