"""Question router — classifies chat questions for hybrid retrieval routing.

Lightweight Haiku call that produces a RoutingHint to guide KG and vector
retrievers on weighting and query strategy.
"""

from __future__ import annotations

from typing import Literal

import structlog
from pydantic import BaseModel

from app.constants import MODEL_ROUTER
from app.integrations.anthropic_client import create_message

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RoutingHint(BaseModel):
    """Structured output from the question router."""

    intent: Literal["lookup", "summarize", "compare", "list", "explain", "follow_up"]
    routing: Literal["factual", "semantic", "mixed"]
    entity_terms: list[str]
    field_terms: list[str]
    time_terms: list[str]
    refers_to_prior: bool


class ChatMessage(BaseModel):
    """Minimal representation of a prior chat turn."""

    role: Literal["user", "assistant"]
    content: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a question classifier for a personal document management system.
The user asks questions about their uploaded documents (passports, certificates,
reports, invoices, etc.). Your job is to classify the question so the retrieval
system knows how to fetch the best context.

Classify the question into a structured hint with these fields:

intent — what the user wants:
  - lookup: a specific fact ("When does Priya's passport expire?")
  - summarize: a summary of a document or topic ("Summarize the marriage cert")
  - compare: comparing facts across documents or entities ("Compare expiry dates")
  - list: enumerate items ("List all my documents", "Show all passports")
  - explain: deeper explanation or reasoning ("Why was the claim rejected?")
  - follow_up: continuing a previous question ("And the expiry date?")

routing — which retrieval path is most useful:
  - factual: structured knowledge graph facts are primary (dates, names, numbers)
  - semantic: full-text document chunks are primary (summaries, explanations)
  - mixed: both sources are equally important (comparisons, complex questions)

entity_terms — raw terms from the question that name people, documents, or
relations (e.g., "Priya", "wife", "passport", "trade licence"). Extract as-is.

field_terms — raw terms that name fields or data points (e.g., "expiry date",
"passport number", "date of birth", "recommendation").

time_terms — date or time references in the question (e.g., "2024", "last year",
"before March"). Empty if no temporal reference.

refers_to_prior — true if the question uses pronouns or references that need
conversation history to resolve ("the", "it", "that one", "she", "his").
"""

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_TOOL_SCHEMA = RoutingHint.model_json_schema()
_TOOL_NAME = "RoutingHint"


async def classify(
    question: str,
    history: list[ChatMessage] | None = None,
) -> RoutingHint:
    """Classify a chat question into a RoutingHint via Haiku."""
    messages: list[dict] = []

    # Include recent history so the model can judge follow-up references
    if history:
        for msg in history[-6:]:
            messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": question})

    response = await create_message(
        model=MODEL_ROUTER,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=messages,
        tools=[
            {
                "name": _TOOL_NAME,
                "description": "Classify the user question for retrieval routing.",
                "input_schema": _TOOL_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
    )

    # Extract tool_use block
    for block in response.content:
        if block.type == "tool_use":
            hint = RoutingHint.model_validate(block.input)
            logger.info(
                "question_routed",
                intent=hint.intent,
                routing=hint.routing,
                entity_terms=hint.entity_terms,
                field_terms=hint.field_terms,
                refers_to_prior=hint.refers_to_prior,
            )
            return hint

    # Fallback — should never happen with tool_choice forced
    logger.warning("router_no_tool_use", question=question[:80])
    return RoutingHint(
        intent="lookup",
        routing="mixed",
        entity_terms=[],
        field_terms=[],
        time_terms=[],
        refers_to_prior=False,
    )
