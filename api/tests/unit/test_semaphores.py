"""Tests for LLM client concurrency caps (P1.5-D3-HARNESS-13).

Verifies:
1. Anthropic semaphore limits concurrent calls to 10
2. OpenAI semaphore limits concurrent calls to 5
3. Calls beyond the cap wait (not rejected)
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_anthropic_semaphore_limits_concurrency():
    """At most 10 Anthropic calls run concurrently; extras queue."""
    concurrent = {"current": 0, "peak": 0}
    gate = asyncio.Event()

    async def slow_create(**kwargs):
        concurrent["current"] += 1
        concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        await gate.wait()
        concurrent["current"] -= 1
        return AsyncMock(content=[AsyncMock(text="ok")])

    with patch("app.integrations.anthropic_client.client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=slow_create)

        from app.integrations.anthropic_client import create_message

        # Launch 15 concurrent calls
        tasks = [asyncio.create_task(create_message(model="m", max_tokens=1, messages=[])) for _ in range(15)]

        # Let them reach the semaphore
        await asyncio.sleep(0.05)

        # Peak should be capped at 10
        assert concurrent["peak"] == 10, f"Peak concurrency {concurrent['peak']} exceeded cap of 10"
        assert concurrent["current"] == 10, f"Expected 10 in-flight, got {concurrent['current']}"

        # Release the gate — remaining 5 should proceed
        gate.set()
        await asyncio.gather(*tasks)

        assert concurrent["current"] == 0


@pytest.mark.asyncio
async def test_openai_semaphore_limits_concurrency():
    """At most 5 OpenAI embedding calls run concurrently; extras queue."""
    concurrent = {"current": 0, "peak": 0}
    gate = asyncio.Event()

    async def slow_embeddings(**kwargs):
        concurrent["current"] += 1
        concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        await gate.wait()
        concurrent["current"] -= 1
        return AsyncMock(data=[AsyncMock(embedding=[0.1, 0.2])])

    with patch("app.integrations.openai_embeddings.client") as mock_client:
        mock_client.embeddings.create = AsyncMock(side_effect=slow_embeddings)

        from app.integrations.openai_embeddings import get_embeddings

        # Launch 8 concurrent calls
        tasks = [asyncio.create_task(get_embeddings(["hello"])) for _ in range(8)]

        await asyncio.sleep(0.05)

        assert concurrent["peak"] == 5, f"Peak concurrency {concurrent['peak']} exceeded cap of 5"
        assert concurrent["current"] == 5, f"Expected 5 in-flight, got {concurrent['current']}"

        gate.set()
        await asyncio.gather(*tasks)

        assert concurrent["current"] == 0
