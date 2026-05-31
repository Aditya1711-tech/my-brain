"""One-time backfill: generate thumbnails for existing documents.

Reads each PDF/image from the original storage path, renders the first page
(PDF via PyMuPDF, images via Pillow), and uploads a 600x800 JPEG thumbnail
to thumbnails/{doc.id}.jpg in the same bucket.

Run from the api/ directory:
    python scripts/backfill_thumbnails.py
"""

import io
import os
import sys

# Allow importing from app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".env"))

from PIL import Image
from supabase import create_client

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "user-uploads")

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Use psycopg2 (sync) to query the DB — asyncpg isn't needed for a script
import re

# Convert postgresql+asyncpg:// → postgresql:// for psycopg2
db_url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", DATABASE_URL)

try:
    import psycopg2
    conn = psycopg2.connect(db_url)
except ImportError:
    print("psycopg2 not available — falling back to listing documents via Supabase storage")
    conn = None

PDF_MIME = "application/pdf"


def render_pdf_first_page(pdf_bytes: bytes) -> bytes:
    """Render first page of a PDF to PNG bytes using PyMuPDF."""
    import fitz  # pymupdf

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    matrix = fitz.Matrix(1.5, 1.5)  # 1.5× scale for better quality
    pix = page.get_pixmap(matrix=matrix)
    return pix.tobytes("png")


def resize_to_thumbnail(img_bytes: bytes) -> bytes:
    """Resize image bytes to at most 600×800 JPEG."""
    img = Image.open(io.BytesIO(img_bytes))
    img = img.convert("RGB")
    img.thumbnail((600, 800), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def process_document(doc_id: str, storage_path: str, mime_type: str) -> bool:
    """Download original, render thumbnail, upload. Returns True on success."""
    # Download original file
    try:
        file_bytes = sb.storage.from_(BUCKET).download(storage_path)
    except Exception as e:
        print(f"  SKIP {doc_id}: download failed — {e}")
        return False

    # Render to image bytes
    try:
        if mime_type == PDF_MIME or mime_type == "application/octet-stream":
            # Try PDF rendering
            try:
                img_bytes = render_pdf_first_page(file_bytes)
            except Exception:
                # Might not be a PDF
                print(f"  SKIP {doc_id}: not renderable as PDF")
                return False
        elif mime_type.startswith("image/"):
            img_bytes = file_bytes
        else:
            print(f"  SKIP {doc_id}: unsupported mime_type={mime_type}")
            return False
    except Exception as e:
        print(f"  SKIP {doc_id}: render failed — {e}")
        return False

    # Resize and upload
    try:
        thumb_bytes = resize_to_thumbnail(img_bytes)
        sb.storage.from_(BUCKET).upload(
            f"thumbnails/{doc_id}.jpg",
            thumb_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
        print(f"  OK   {doc_id}")
        return True
    except Exception as e:
        print(f"  FAIL {doc_id}: upload failed — {e}")
        return False


def main() -> None:
    docs: list[tuple[str, str, str]] = []  # (id, storage_path, mime_type)

    if conn is not None:
        cur = conn.cursor()
        cur.execute("""
            SELECT id::text, storage_path, mime_type
            FROM documents
            WHERE status = 'ready'
              AND deleted_at IS NULL
              AND mime_type IN ('application/pdf', 'image/jpeg', 'image/png',
                                'image/gif', 'image/webp', 'image/tiff',
                                'application/octet-stream')
            ORDER BY created_at DESC
        """)
        docs = cur.fetchall()
        print(f"Found {len(docs)} documents to backfill")
    else:
        print("No DB connection — cannot enumerate documents. Exiting.")
        return

    ok = fail = skip = 0
    for doc_id, storage_path, mime_type in docs:
        print(f"Processing {doc_id} ({mime_type})")
        result = process_document(doc_id, storage_path, mime_type)
        if result:
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} succeeded, {fail} failed/skipped")


if __name__ == "__main__":
    main()
