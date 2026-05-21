from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_VERIFIER


class FieldVerification(BaseModel):
    field_name: str
    confidence: float
    needs_retry: bool
    reasoning: str


class VerificationOutput(BaseModel):
    fields: list[FieldVerification]
    overall_quality: float


class VerifierInput(BaseModel):
    document_type: str
    schema_fields: list[dict]
    extracted_fields: list[dict]
    text_sample: str


class VerifierAgent(Agent[VerifierInput, VerificationOutput]):
    name = "verifier"
    model = MODEL_VERIFIER
    prompt_file = "verifier.md"
    output_schema = VerificationOutput


verifier_agent = VerifierAgent()
