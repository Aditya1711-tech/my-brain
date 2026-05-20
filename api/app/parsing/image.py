from app.services.documents.types import RawExtraction


def parse_image(file_bytes: bytes, filename: str) -> RawExtraction:
    """Load image bytes — no OCR yet. Multimodal Sonnet handles text extraction.

    Returns the image as a single "page image" for the extractor agent.
    """
    return RawExtraction(
        text="",
        page_images=[file_bytes],
        page_count=1,
    )
