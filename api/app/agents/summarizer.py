"""Summarizer agent — generates a short factual summary of a document.

Uses Haiku for speed and cost (~150 token output target).
Part of D-SUMMARY-01 (Phase 1.5).
"""

from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_SUMMARIZER


class SummarizerInput(BaseModel):
    document_type: str
    text_sample: str


class SummaryOutput(BaseModel):
    summary: str


class SummarizerAgent(Agent[SummarizerInput, SummaryOutput]):
    name = "summarizer"
    model = MODEL_SUMMARIZER
    prompt_file = "summarizer.md"
    output_schema = SummaryOutput
    max_tokens = 300
