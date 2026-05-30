import asyncio

from openai import AsyncOpenAI

from app.config import settings
from app.constants import MODEL_EMBEDDINGS
from app.utils.retry import retry_on_transient

client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

# Process-level concurrency cap — protects against rate-limit storms
_semaphore = asyncio.Semaphore(5)


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings with concurrency cap + retry on transient errors."""
    async with _semaphore:
        response = await retry_on_transient(
            client.embeddings.create,
            model=MODEL_EMBEDDINGS,
            input=texts,
        )
        return [item.embedding for item in response.data]
