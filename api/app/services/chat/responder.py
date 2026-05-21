"""Stream Claude responses with citations."""

import json
from collections.abc import AsyncGenerator

from app.constants import MODEL_CHAT
from app.integrations.anthropic_client import client as anthropic_client


async def stream_response(
    question: str,
    chunks: list[dict],
    scope: str = "document",
    kg_context: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream an SSE response from Claude with chunk citations.

    Yields SSE-formatted strings: 'data: {...}\n\n'
    Event types: text_delta, citation, done, error
    """
    # Build context from retrieved chunks
    context_parts = []
    if kg_context:
        context_parts.append(f"Knowledge Graph Facts:\n{kg_context}\n")

    for i, chunk in enumerate(chunks):
        source = chunk.get("filename", f"chunk {chunk['chunk_index']}")
        context_parts.append(f"[Source {i + 1}: {source}]\n{chunk['text']}\n")

    context = "\n---\n".join(context_parts)

    system_prompt = (
        "You are a helpful assistant answering questions about the user's documents. "
        "Use ONLY the provided context to answer. If the context doesn't contain "
        "enough information, say so clearly.\n\n"
        "When you reference information from the context, cite the source using "
        "[Source N] format inline. Be concise and accurate.\n\n"
    )
    if kg_context:
        system_prompt += (
            "Knowledge Graph facts are authoritative — prefer them over chunk text "
            "when both are available for the same data point.\n\n"
        )

    user_message = f"Context:\n{context}\n\nQuestion: {question}"

    try:
        # Emit citation metadata first
        for i, chunk in enumerate(chunks):
            citation_event = {
                "type": "citation",
                "index": i + 1,
                "chunk_id": chunk["id"],
                "chunk_index": chunk["chunk_index"],
                "document_id": chunk.get("document_id"),
                "filename": chunk.get("filename"),
            }
            yield f"data: {json.dumps(citation_event)}\n\n"

        async with anthropic_client.messages.stream(
            model=MODEL_CHAT,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text_delta', 'text': text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
