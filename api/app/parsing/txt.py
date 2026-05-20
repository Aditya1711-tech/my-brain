from app.services.documents.types import RawExtraction


def parse_txt(file_bytes: bytes, filename: str) -> RawExtraction:
    """Parse a plain text file."""
    text = file_bytes.decode("utf-8", errors="replace")
    return RawExtraction(
        text=text,
        page_count=1,
    )
