"""Search endpoint — resolve terms into chips and query documents."""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.deps import DbSession, VerifiedUser

router = APIRouter()


class SearchRequest(BaseModel):
    term: str | None = None
    chips: list[dict] = []


class SearchResponse(BaseModel):
    chip: dict | None = None
    documents: list[dict]


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, db: DbSession, user_id: VerifiedUser) -> SearchResponse:
    """Resolve a search term into a chip and return filtered documents."""
    from app.services.search.resolver import SearchResolver
    from app.services.search.query import search_documents
    chips = list(req.chips)
    new_chip = None

    # Resolve new term if provided
    if req.term and req.term.strip():
        resolver = SearchResolver(db, user_id)
        resolved = await resolver.resolve(req.term.strip())
        new_chip = resolved.to_dict()
        chips.append(new_chip)

    # Execute search with all chips
    if chips:
        documents = await search_documents(db, user_id, chips)
    else:
        # No chips — return recent documents
        from sqlalchemy import text

        result = await db.execute(
            text("""
                SELECT id, original_filename, file_type, status, doc_type,
                       domain, summary, created_at
                FROM documents
                WHERE user_id = :uid AND deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 50
            """),
            {"uid": str(user_id)},
        )
        documents = [dict(row) for row in result.mappings().fetchall()]

    # Serialize UUIDs and datetimes
    serialized = []
    for doc in documents:
        serialized.append({
            k: str(v) if hasattr(v, "hex") or hasattr(v, "isoformat") else v
            for k, v in doc.items()
        })

    return SearchResponse(chip=new_chip, documents=serialized)
