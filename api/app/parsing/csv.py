import csv
import io

from app.services.documents.types import RawExtraction


def parse_csv(file_bytes: bytes, filename: str) -> RawExtraction:
    """Parse a CSV file into text and a table structure."""
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]

    tables = [rows] if rows else []

    return RawExtraction(
        text=text,
        tables=tables,
        page_count=1,
        structured={"rows": len(rows)},
    )
