import io

import structlog

from app.services.documents.types import RawExtraction

logger = structlog.get_logger()


def parse_pdf(file_bytes: bytes, filename: str) -> RawExtraction:
    """Extract text, tables, and page images from a PDF.

    Strategy:
    1. Try pdfplumber for text + tables
    2. If text is sparse (< 50 chars), fall back to page-as-image for multimodal extraction
    3. Use pikepdf for password-protected PDFs
    """
    import pdfplumber
    import fitz  # pymupdf

    raw_bytes = _try_unlock(file_bytes)
    text_parts: list[str] = []
    tables: list[list[list[str]]] = []
    page_images: list[bytes] = []

    # pdfplumber pass — text + tables
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

            for table in page.extract_tables():
                cleaned = [
                    [cell or "" for cell in row]
                    for row in table
                    if row
                ]
                if cleaned:
                    tables.append(cleaned)

    full_text = "\n\n".join(text_parts).strip()

    # If text is sparse, render pages as images for multimodal fallback
    if len(full_text) < 50:
        logger.info("pdf_sparse_text_fallback", filename=filename, text_len=len(full_text))
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            page_images.append(pix.tobytes("png"))
        doc.close()

    return RawExtraction(
        text=full_text,
        tables=tables,
        page_images=page_images,
        page_count=page_count,
    )


def _try_unlock(file_bytes: bytes) -> bytes:
    """Attempt to unlock a password-protected PDF with an empty password."""
    try:
        import pikepdf

        pdf = pikepdf.open(io.BytesIO(file_bytes), password="")
        out = io.BytesIO()
        pdf.save(out)
        pdf.close()
        return out.getvalue()
    except Exception:
        return file_bytes
