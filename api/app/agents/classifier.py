import base64
from typing import Literal

from pydantic import BaseModel

from app.agents.base import Agent
from app.constants import MODEL_CLASSIFIER


class EntityHint(BaseModel):
    name: str
    type: Literal["person", "organization", "asset", "other"]
    role: Literal["subject", "author", "mentioned", "witness", "other"]


class ClassifierInput(BaseModel):
    text_sample: str
    has_image: bool = False


class ClassifierOutput(BaseModel):
    document_type: str
    domain: Literal[
        "personal", "medical", "legal", "financial", "professional", "educational", "other"
    ]
    country: str | None = None
    primary_language: str
    is_scanned: bool
    is_handwritten: bool
    is_digital: bool
    has_clear_text: bool
    entity_hints: list[EntityHint]


class ClassifierAgent(Agent[ClassifierInput, ClassifierOutput]):
    name = "classifier"
    model = MODEL_CLASSIFIER
    prompt_file = "classifier.md"
    output_schema = ClassifierOutput

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

    def _build_messages(self, input_data: ClassifierInput, **kwargs: object) -> list[dict]:
        """Build messages — include image if provided via page_image kwarg."""
        system_prompt = self._load_prompt()
        content: list[dict] = []
        page_image: bytes | None = kwargs.get("page_image")  # type: ignore[assignment]

        if page_image:
            b64 = base64.b64encode(page_image).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self._detect_media_type(page_image),
                    "data": b64,
                },
            })

        content.append({
            "type": "text",
            "text": f"{system_prompt}\n\n---\n\nDocument text (first 2 pages):\n{input_data.text_sample[:6000]}",
        })

        return [{"role": "user", "content": content}]
