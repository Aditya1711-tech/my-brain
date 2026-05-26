"""Tests for utils/retry.py — transient-error retry with backoff (D-LLM-RETRY-01).

Verifies:
- Transient errors (429, 500, 502, 503, 504) are retried up to max_attempts
- Permanent errors (400, 401, 404) are NOT retried
- Connection/timeout errors are retried
- Backoff delays are correct (exponential with cap)
- Successful result is returned after transient failures
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.retry import is_transient, retry_on_transient


# -- Helpers ------------------------------------------------------------------

class FakeAPIError(Exception):
    """Simulates an SDK error with a status_code attribute."""
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


class FakeConnectionError(Exception):
    """Simulates a connection error (name contains 'Connection')."""
    pass


class FakeTimeoutError(Exception):
    """Simulates a timeout error (name contains 'Timeout')."""
    pass


# -- is_transient tests -------------------------------------------------------

@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_status_codes(code: int):
    assert is_transient(FakeAPIError(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_permanent_status_codes(code: int):
    assert is_transient(FakeAPIError(code)) is False


def test_connection_error_is_transient():
    assert is_transient(FakeConnectionError()) is True


def test_timeout_error_is_transient():
    assert is_transient(FakeTimeoutError()) is True


def test_generic_error_is_not_transient():
    assert is_transient(ValueError("bad input")) is False


# -- retry_on_transient tests -------------------------------------------------

@pytest.mark.asyncio
async def test_succeeds_first_try():
    fn = AsyncMock(return_value="ok")
    result = await retry_on_transient(fn, _max_attempts=3)
    assert result == "ok"
    assert fn.call_count == 1


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    fn = AsyncMock(side_effect=[FakeAPIError(429), FakeAPIError(429), "ok"])
    with patch("app.utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_on_transient(fn, _max_attempts=3, _base_delay=1.0)
    assert result == "ok"
    assert fn.call_count == 3
    # Verify exponential backoff: 1s, 2s
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0].args[0] == 1.0
    assert mock_sleep.call_args_list[1].args[0] == 2.0


@pytest.mark.asyncio
async def test_raises_after_max_attempts_exhausted():
    fn = AsyncMock(side_effect=FakeAPIError(500))
    with (
        patch("app.utils.retry.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(FakeAPIError),
    ):
        await retry_on_transient(fn, _max_attempts=3, _base_delay=0.01)
    assert fn.call_count == 3


@pytest.mark.asyncio
async def test_permanent_error_not_retried():
    fn = AsyncMock(side_effect=FakeAPIError(400))
    with pytest.raises(FakeAPIError):
        await retry_on_transient(fn, _max_attempts=3)
    assert fn.call_count == 1, "Permanent error (400) should NOT be retried"


@pytest.mark.asyncio
async def test_connection_error_retried():
    fn = AsyncMock(side_effect=[FakeConnectionError(), "ok"])
    with patch("app.utils.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_on_transient(fn, _max_attempts=3, _base_delay=0.01)
    assert result == "ok"
    assert fn.call_count == 2


@pytest.mark.asyncio
async def test_backoff_capped_at_max_delay():
    """With base=1, cap=4: delays should be 1, 2, 4, 4 (capped)."""
    fn = AsyncMock(
        side_effect=[FakeAPIError(429)] * 4 + ["ok"]
    )
    with patch("app.utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_on_transient(
            fn, _max_attempts=5, _base_delay=1.0, _max_delay=4.0,
        )
    assert result == "ok"
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert delays == [1.0, 2.0, 4.0, 4.0]


@pytest.mark.asyncio
async def test_passes_args_and_kwargs():
    fn = AsyncMock(return_value="result")
    await retry_on_transient(fn, "arg1", "arg2", key="val")
    fn.assert_called_once_with("arg1", "arg2", key="val")
