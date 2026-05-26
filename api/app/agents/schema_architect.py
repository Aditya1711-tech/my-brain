from typing import Literal

from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_SCHEMA_ARCHITECT


class SchemaArchitectInput(BaseModel):
    document_type: str
    domain: str
    text_sample: str


class SchemaField(BaseModel):
    name: str
    field_type: Literal[
        "string", "number", "date", "enum", "identifier", "currency_amount", "boolean"
    ]
    description: str
    required: bool
    is_entity_field: bool
    importance: Literal["critical", "important", "nice_to_have"] = "important"
    enum_values: list[str] | None = None


class SchemaOutput(BaseModel):
    document_type: str
    fields: list[SchemaField]
    entity_extraction_required: bool
    notes: str | None = None


class SchemaArchitectAgent(Agent[SchemaArchitectInput, SchemaOutput]):
    name = "schema_architect"
    model = MODEL_SCHEMA_ARCHITECT
    prompt_file = "schema_architect.md"
    output_schema = SchemaOutput
