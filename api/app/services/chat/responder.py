"""Stream Claude responses with structured context and conversation history.

Phase 1.5 upgrade: accepts ContextItem list (KG facts + chunks) instead of
raw chunk dicts. Supports multi-turn conversation via thread history.
Dual-citation contract: [F1]/[F2] for KG facts, [C1]/[C2] for chunks.
"""

import json
from collections.abc import AsyncGenerator

from app.constants import MODEL_CHAT
from app.integrations.anthropic_client import client as anthropic_client
from app.services.chat.fusion import ContextItem

_SYSTEM_PROMPT = """\
You are answering questions about the user's documents.

You have two kinds of context:
1. KNOWLEDGE GRAPH FACTS: structured, authoritative records extracted from documents. Treat these as truth.
2. DOCUMENT CHUNKS: relevant excerpts for context, surrounding detail, and nuance.

Rules:
- If KG facts directly answer the question, lead with them and cite the source document.
- Use chunks for elaboration, surrounding context, and questions that aren't simple facts.
- Cite every claim. Use [F1], [F2] for facts and [C1], [C2] for chunks. Citation IDs match the order of context items provided.
- Never invent facts. If neither source supports an answer, say "I don't have that in your documents."
- Be concise. Aim for 1-3 sentences unless the user asked for more detail.
- For follow-up questions, treat pronouns ("the", "that", "she") as referring to entities or documents mentioned in earlier turns.\
"""

_SYSTEM_PROMPT_NO_KG = """\
You are answering questions about the user's documents.

You have DOCUMENT CHUNKS: relevant excerpts for context and detail.

Rules:
- Cite every claim using [C1], [C2], etc. matching the order of context items.
- Never invent facts. If the context doesn't support an answer, say so.
- Be concise. Aim for 1-3 sentences unless the user asked for more detail.
- For follow-up questions, treat pronouns as referring to entities mentioned in earlier turns.\
"""


def _render_context(items: list[ContextItem]) -> str:
    """Render context items into a labeled block for the LLM."""
    parts: list[str] = []
    fact_idx = 0
    chunk_idx = 0

    for item in items:
        if item.type == "kg_fact":
            fact_idx += 1
            parts.append(f"[F{fact_idx}] {item.content}")
        else:
            chunk_idx += 1
            parts.append(f"[C{chunk_idx}] {item.content}")

    return "\n\n".join(parts)


async def stream_response(
    *,
    question: str,
    context_items: list[ContextItem],
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream an SSE response from Claude with dual-citation context.

    Yields SSE-formatted strings: 'data: {...}\\n\\n'
    Event types: citation, text_delta, done, error
    """
    has_kg = any(ci.type == "kg_fact" for ci in context_items)

    try:
        # 1. Emit citation metadata first
        for ci in context_items:
            yield _sse("citation", ci.citation.model_dump(mode="json"))

        # 2. Build messages array with conversation history
        system_prompt = _SYSTEM_PROMPT if has_kg else _SYSTEM_PROMPT_NO_KG
        context_block = _render_context(context_items)
        messages: list[dict] = []

        # Replay history (alternating user/assistant)
        if history:
            for h in history[-12:]:
                messages.append({"role": h["role"], "content": h["content"]})

        # Current turn with context
        messages.append({
            "role": "user",
            "content": f"Context:\n{context_block}\n\n---\n\nQuestion: {question}",
        })

        # 3. Stream
        async with anthropic_client.messages.stream(
            model=MODEL_CHAT,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield _sse("text_delta", {"text": text})

        yield _sse("done", {})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


def _sse(event_type: str, data: dict) -> str:
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"
