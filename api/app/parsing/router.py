import structlog

from app.parsing.csv import parse_csv
from app.parsing.docx import parse_docx
from app.parsing.image import parse_image
from app.parsing.pdf import parse_pdf
from app.parsing.pptx import parse_pptx
from app.parsing.txt import parse_txt
from app.parsing.xlsx import parse_xlsx
from app.services.documents.types import RawExtraction

logger = structlog.get_logger()

_PARSERS: dict[str, callable] = {  # type: ignore[type-arg]
    "application/pdf": parse_pdf,
    "image/png": parse_image,
    "image/jpeg": parse_image,
    "image/webp": parse_image,
    "image/tiff": parse_image,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": parse_docx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": parse_xlsx,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": parse_pptx,
    "text/csv": parse_csv,
    "text/plain": parse_txt,
}


def parse_file(file_bytes: bytes, mime_type: str, filename: str) -> RawExtraction:
    """Route a file to the appropriate parser based on MIME type."""
    parser = _PARSERS.get(mime_type)
    if parser is None:
        logger.warning("no_parser", mime_type=mime_type, filename=filename)
        return RawExtraction(text="[Unsupported file type]")

    logger.info("parsing_file", mime_type=mime_type, filename=filename)
    return parser(file_bytes, filename)
