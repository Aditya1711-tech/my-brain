from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.worker.tasks import process_document_dummy


def parse_redis_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into arq RedisSettings."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
    )


class WorkerSettings:
    """arq worker configuration."""

    functions = [process_document_dummy]
    redis_settings = parse_redis_url(settings.redis_url)
    max_jobs = 5
    job_timeout = 300  # 5 minutes per job
