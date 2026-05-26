"""Transient-error retry with exponential backoff.

Policy (from 00-RULES-1.5.md):
- Max 3 attempts, base delay 1s, cap 8s
- Retry only transient errors: 429, 500, 502, 503, 504, connection errors
- Permanent errors (400, schema validation) do NOT retry
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import structlog

logger = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def is_transient(exc: Exception) -> bool:
    """Return True if the error is transient and safe to retry."""
    # Anthropic/OpenAI SDK errors carry a status_code attribute
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code in TRANSIENT_STATUS_CODES

    # Connection and timeout errors (httpx, aiohttp, stdlib)
    type_name = type(exc).__name__
    if "Connection" in type_name or "Timeout" in type_name:
        return True

    return False


async def retry_on_transient(
    fn: Callable[P, Awaitable[T]],
    *args: P.args,
    _max_attempts: int = 3,
    _base_delay: float = 1.0,
    _max_delay: float = 8.0,
    **kwargs: P.kwargs,
) -> T:
    """Call an async function with retry on transient errors.

    Exponential backoff: delay = min(base_delay * 2^attempt, max_delay).
    Underscore-prefixed control params avoid collision with the wrapped fn's kwargs.
    """
    last_exc: Exception | None = None

    for attempt in range(_max_attempts):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if not is_transient(exc) or attempt == _max_attempts - 1:
                raise
            delay = min(_base_delay * (2**attempt), _max_delay)
            logger.warning(
                "retry_transient",
                attempt=attempt + 1,
                max_attempts=_max_attempts,
                delay_s=delay,
                error_type=type(exc).__name__,
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]  # unreachable; satisfies type checker
