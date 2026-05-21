import base64
import json

from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_EXTRACTOR
from app.integrations.anthropic_client import client as anthropic_client


class ExtractedField(BaseModel):
    name: str
    value: str | None = None
    raw_value: str | None = None
    source_location: str | None = None


class ExtractedEntity(BaseModel):
    name: str
    type: str
    role: str
    fields: dict[str, str] = {}


class ExtractorInput(BaseModel):
    schema_fields: list[dict]  # SchemaField dicts
    document_type: str
    text: str
    has_images: bool = False
    retry_fields: list[str] | None = None
    retry_feedback: str | None = None


class ExtractionOutput(BaseModel):
    fields: list[ExtractedField]
    detected_entities: list[ExtractedEntity]


class ExtractorAgent(Agent[ExtractorInput, ExtractionOutput]):
    name = "extractor"
    model = MODEL_EXTRACTOR
    prompt_file = "extractor.md"
    output_schema = ExtractionOutput

    def __init__(self) -> None:
        self._page_images: list[bytes] = []

    def set_page_images(self, images: list[bytes]) -> None:
        """Set page images for multimodal extraction."""
        self._page_images = images

    def _build_messages(self, input_data: ExtractorInput) -> list[dict]:
        """Build messages — include images if available."""
        system_prompt = self._load_prompt()
        content: list[dict] = []

        # Add page images (up to 5 pages)
        for img in self._page_images[:5]:
            b64 = base64.b64encode(img).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            })

        # Build text prompt
        schema_text = json.dumps(input_data.schema_fields, indent=2)
        prompt_parts = [
            system_prompt,
            f"\n\n---\n\nDocument type: {input_data.document_type}",
            f"\n\nExtraction schema:\n{schema_text}",
            f"\n\nDocument text:\n{input_data.text[:8000]}",
        ]

        if input_data.retry_fields:
            prompt_parts.append(
                f"\n\n--- RETRY ---\n"
                f"This is a RETRY for specific fields that previous extraction got wrong.\n"
                f"Fields to re-examine: {', '.join(input_data.retry_fields)}\n"
                f"Verifier feedback: {input_data.retry_feedback or 'N/A'}\n\n"
                f"Focus only on these fields. Look more carefully at the image. "
                f"Consider alternative interpretations.\n"
                f"Return values for ALL schema fields, but pay particular attention to the flagged ones."
            )

        content.append({"type": "text", "text": "\n".join(prompt_parts)})

        return [{"role": "user", "content": content}]


extractor_agent = ExtractorAgent()
