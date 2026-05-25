from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_KNOWLEDGE_INTEGRATOR


class EntityResolution(BaseModel):
    detected_name: str
    detected_type: str
    decision: str  # match_existing | create_new | uncertain
    matched_entity_id: str | None = None
    new_canonical_name: str | None = None
    aliases_to_add: list[str] = []
    reasoning: str


class FactToWrite(BaseModel):
    entity_id_placeholder: str  # references detected_name in EntityResolution
    field_name: str
    field_value: str
    field_type: str
    confidence: float


class RelationshipToWrite(BaseModel):
    from_entity_placeholder: str
    to_entity_placeholder: str
    relation_type: str


class KnowledgeIntegratorInput(BaseModel):
    document_type: str
    detected_entities: list[dict]  # ExtractedEntity dicts from extractor
    extracted_fields: list[dict]  # field dicts with name/value/type
    existing_entities: list[dict]  # candidate entities from DB for resolution


class IntegrationOutput(BaseModel):
    resolutions: list[EntityResolution]
    facts: list[FactToWrite]
    relationships: list[RelationshipToWrite]


class KnowledgeIntegratorAgent(Agent[KnowledgeIntegratorInput, IntegrationOutput]):
    name = "knowledge_integrator"
    model = MODEL_KNOWLEDGE_INTEGRATOR
    prompt_file = "knowledge_integrator.md"
    output_schema = IntegrationOutput
