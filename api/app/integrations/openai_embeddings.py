from openai import AsyncOpenAI

from app.config import settings
from app.constants import MODEL_EMBEDDINGS
from app.utils.retry import retry_on_transient

client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings with retry on transient errors (429/5xx)."""
    response = await retry_on_transient(
        client.embeddings.create,
        model=MODEL_EMBEDDINGS,
        input=texts,
    )
    return [item.embedding for item in response.data]
