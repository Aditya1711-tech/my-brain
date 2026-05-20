from dataclasses import dataclass, field


@dataclass
class RawExtraction:
    """Output of a file-type-specific parser."""

    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)  # list of tables, each a 2D grid
    page_images: list[bytes] = field(default_factory=list)  # page-as-image fallback (PNG bytes)
    page_count: int = 0
    structured: dict = field(default_factory=dict)  # e.g., spreadsheet sheet data
