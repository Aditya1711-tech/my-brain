from openai import AsyncOpenAI

from app.config import settings
from app.constants import MODEL_EMBEDDINGS

client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a batch of texts."""
    response = await client.embeddings.create(
        model=MODEL_EMBEDDINGS,
        input=texts,
    )
    return [item.embedding for item in response.data]
