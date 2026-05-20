import anthropic

from app.config import settings

client = anthropic.AsyncAnthropic(
    api_key=settings.anthropic_api_key.get_secret_value(),
)
