import base64
import json

from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_EXTRACTOR


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

    @staticmethod
    def _detect_media_type(data: bytes) -> str:
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        if data[:3] == b"GIF":
            return "image/gif"
        return "image/png"

    def _build_messages(self, input_data: ExtractorInput, **kwargs: object) -> list[dict]:
        """Build messages — include images if provided via page_images kwarg."""
        system_prompt = self._load_prompt()
        content: list[dict] = []
        page_images: list[bytes] = kwargs.get("page_images") or []  # type: ignore[assignment]

        # Add page images (up to 5 pages)
        for img in page_images[:5]:
            b64 = base64.b64encode(img).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self._detect_media_type(img),
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
