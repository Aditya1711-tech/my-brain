"""Fusion layer — merges KG facts and chunks into ordered context items.

Takes KGFact rows and chunk dicts, produces a single ordered list of
ContextItem objects for the responder.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.services.chat.kg_retriever import KGFact
from app.services.chat.router import RoutingHint


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    type: Literal["kg_fact", "chunk"]
    # KG fact fields
    entity_id: UUID | None = None
    field_name: str | None = None
    source_document_id: UUID | None = None
    # Chunk fields
    chunk_id: str | None = None
    document_id: str | None = None
    filename: str | None = None


class ContextItem(BaseModel):
    type: Literal["kg_fact", "chunk"]
    content: str
    citation: Citation
    weight: float


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

# Rough token estimate: 1 token ≈ 4 chars
_MAX_CONTEXT_CHARS = 3000 * 4  # ~3000 tokens


def fuse(
    kg_facts: list[KGFact],
    chunks: list[dict],
    hint: RoutingHint,
) -> list[ContextItem]:
    """Merge KG facts and chunks into a weighted, deduped, budget-clipped context list."""
    items: list[ContextItem] = []

    # Render KG facts
    for fact in kg_facts:
        items.append(ContextItem(
            type="kg_fact",
            content=(
                f"{fact.entity_name} — {fact.field_name}: {fact.field_value} "
                f"(source: {fact.source_document_name})"
            ),
            citation=Citation(
                type="kg_fact",
                entity_id=fact.entity_id,
                field_name=fact.field_name,
                source_document_id=fact.source_document_id,
            ),
            weight=1.0 if hint.routing in ("factual", "mixed") else 0.6,
        ))

    # Render chunks
    for chunk in chunks:
        filename = chunk.get("filename", f"chunk {chunk.get('chunk_index', '?')}")
        items.append(ContextItem(
            type="chunk",
            content=f"[from {filename}]: {chunk['text']}",
            citation=Citation(
                type="chunk",
                chunk_id=chunk.get("id"),
                document_id=chunk.get("document_id"),
                filename=filename,
            ),
            weight=1.0 if hint.routing in ("semantic", "mixed") else 0.5,
        ))

    # Dedupe: if a chunk text contains a KG fact value, lower the chunk's weight
    items = _dedupe_overlapping(items)

    # Sort by weight descending
    items.sort(key=lambda x: x.weight, reverse=True)

    # Budget clip
    items = _budget_clip(items, _MAX_CONTEXT_CHARS)

    return items


def _dedupe_overlapping(items: list[ContextItem]) -> list[ContextItem]:
    """If a chunk contains the exact value of a KG fact, lower its weight."""
    fact_values: set[str] = set()
    for item in items:
        if item.type == "kg_fact" and item.citation.field_name:
            # Extract the value portion after ": "
            parts = item.content.split(": ", 1)
            if len(parts) > 1:
                val = parts[1].split(" (source:")[0].strip()
                if len(val) > 2:
                    fact_values.add(val.lower())

    if not fact_values:
        return items

    result = []
    for item in items:
        if item.type == "chunk":
            chunk_lower = item.content.lower()
            if any(fv in chunk_lower for fv in fact_values):
                # Redundant chunk — demote rather than remove
                item = item.model_copy(update={"weight": item.weight * 0.5})
        result.append(item)
    return result


def _budget_clip(items: list[ContextItem], max_chars: int) -> list[ContextItem]:
    """Keep top items that fit within the character budget."""
    result = []
    total = 0
    for item in items:
        item_len = len(item.content)
        if total + item_len > max_chars and result:
            break
        result.append(item)
        total += item_len
    return result
