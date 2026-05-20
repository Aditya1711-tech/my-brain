from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentCreate:
    """DTO for inserting a new document."""

    def __init__(
        self,
        user_id: UUID,
        file_hash: str,
        original_filename: str,
        mime_type: str,
        file_type: str,
        size_bytes: int,
        storage_path: str,
        folder_id: UUID | None = None,
        user_note: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.file_hash = file_hash
        self.original_filename = original_filename
        self.mime_type = mime_type
        self.file_type = file_type
        self.size_bytes = size_bytes
        self.storage_path = storage_path
        self.folder_id = folder_id
        self.user_note = user_note


class DocumentRow:
    """Lightweight mapping of a document row."""

    def __init__(self, row: dict) -> None:
        self.id: UUID = row["id"]
        self.user_id: UUID = row["user_id"]
        self.status: str = row["status"]
        self.file_hash: str = row["file_hash"]
        self.original_filename: str = row["original_filename"]
        self.mime_type: str = row["mime_type"]
        self.file_type: str = row["file_type"]
        self.size_bytes: int = row["size_bytes"]
        self.storage_path: str = row["storage_path"]


class DocumentsRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, dto: DocumentCreate) -> UUID:
        """Insert a new document. Returns the generated id."""
        result = await self.db.execute(
            text("""
                INSERT INTO documents (
                    user_id, file_hash, original_filename, mime_type,
                    file_type, size_bytes, storage_path, folder_id, user_note
                ) VALUES (
                    :user_id, :file_hash, :original_filename, :mime_type,
                    :file_type, :size_bytes, :storage_path, :folder_id, :user_note
                )
                RETURNING id
            """),
            {
                "user_id": str(dto.user_id),
                "file_hash": dto.file_hash,
                "original_filename": dto.original_filename,
                "mime_type": dto.mime_type,
                "file_type": dto.file_type,
                "size_bytes": dto.size_bytes,
                "storage_path": dto.storage_path,
                "folder_id": str(dto.folder_id) if dto.folder_id else None,
                "user_note": dto.user_note,
            },
        )
        row = result.fetchone()
        await self.db.commit()
        return row[0]  # type: ignore[index]

    async def get(self, user_id: UUID, doc_id: UUID) -> DocumentRow | None:
        """Get a single document by id, scoped to user."""
        result = await self.db.execute(
            text("""
                SELECT id, user_id, status, file_hash, original_filename,
                       mime_type, file_type, size_bytes, storage_path
                FROM documents
                WHERE id = :doc_id AND user_id = :user_id AND deleted_at IS NULL
            """),
            {"doc_id": str(doc_id), "user_id": str(user_id)},
        )
        row = result.mappings().fetchone()
        return DocumentRow(dict(row)) if row else None

    async def get_by_id(self, doc_id: UUID) -> DocumentRow | None:
        """Get a document by id (service-role, no user filter)."""
        result = await self.db.execute(
            text("""
                SELECT id, user_id, status, file_hash, original_filename,
                       mime_type, file_type, size_bytes, storage_path
                FROM documents
                WHERE id = :doc_id AND deleted_at IS NULL
            """),
            {"doc_id": str(doc_id)},
        )
        row = result.mappings().fetchone()
        return DocumentRow(dict(row)) if row else None

    async def update_status(
        self,
        doc_id: UUID,
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        """Transition document to a new status."""
        await self.db.execute(
            text("""
                UPDATE documents
                SET status = :status,
                    failure_reason = :failure_reason,
                    updated_at = now()
                WHERE id = :doc_id
            """),
            {
                "doc_id": str(doc_id),
                "status": status,
                "failure_reason": failure_reason,
            },
        )
        await self.db.commit()

    async def exists_by_hash(self, user_id: UUID, file_hash: str) -> bool:
        """Check if user already uploaded a file with this hash."""
        result = await self.db.execute(
            text("""
                SELECT 1 FROM documents
                WHERE user_id = :user_id AND file_hash = :file_hash AND deleted_at IS NULL
                LIMIT 1
            """),
            {"user_id": str(user_id), "file_hash": file_hash},
        )
        return result.fetchone() is not None
