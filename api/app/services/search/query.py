"""Build SQL queries from search chips — hybrid BM25 + vector search."""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.openai_embeddings import get_embeddings

logger = structlog.get_logger()


async def search_documents(
    db: AsyncSession,
    user_id: UUID,
    chips: list[dict],
) -> list[dict]:
    """Execute a search from a list of resolved chips. Returns document dicts."""
    uid = str(user_id)

    # Build WHERE conditions from chips
    conditions = ["d.user_id = :uid", "d.deleted_at IS NULL"]
    params: dict = {"uid": uid}
    joins: list[str] = []
    has_content_chip = False
    content_term = ""

    for i, chip in enumerate(chips):
        facet = chip["facet"]
        value = chip["value"]

        if facet == "file_type":
            conditions.append(f"d.file_type = :ft_{i}")
            params[f"ft_{i}"] = value

        elif facet == "doc_type":
            conditions.append(f"d.doc_type = :dt_{i}")
            params[f"dt_{i}"] = value

        elif facet == "domain":
            conditions.append(f"d.domain = :dom_{i}")
            params[f"dom_{i}"] = value

        elif facet == "folder":
            conditions.append(f"d.folder_id = :fld_{i}")
            params[f"fld_{i}"] = value

        elif facet == "tag":
            joins.append(
                f"JOIN document_tags dt_{i} ON dt_{i}.document_id = d.id AND dt_{i}.tag_id = :tag_{i}"
            )
            params[f"tag_{i}"] = value

        elif facet == "entity":
            joins.append(
                f"JOIN document_entities de_{i} ON de_{i}.document_id = d.id AND de_{i}.entity_id = :ent_{i}"
            )
            params[f"ent_{i}"] = value

        elif facet == "relation":
            # Find documents linked to entities that have this relation type
            joins.append(
                f"JOIN document_entities drel_{i} ON drel_{i}.document_id = d.id"
                f" JOIN entity_relationships erel_{i} ON"
                f" (erel_{i}.from_entity_id = drel_{i}.entity_id OR erel_{i}.to_entity_id = drel_{i}.entity_id)"
                f" AND erel_{i}.relation_type = :rel_{i}"
            )
            params[f"rel_{i}"] = value

        elif facet == "content":
            has_content_chip = True
            content_term = value

    # Build the query
    if has_content_chip and content_term:
        # Hybrid search: BM25 + vector similarity
        return await _hybrid_search(db, conditions, joins, params, content_term, uid)
    else:
        # Facet-only search
        join_clause = " ".join(joins)
        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT d.id, d.original_filename, d.file_type, d.status, d.doc_type,
                   d.domain, d.summary, d.created_at
            FROM documents d
            {join_clause}
            WHERE {where_clause}
            ORDER BY d.created_at DESC
            LIMIT 50
        """
        result = await db.execute(text(query), params)
        return [dict(row) for row in result.mappings().fetchall()]


async def _hybrid_search(
    db: AsyncSession,
    conditions: list[str],
    joins: list[str],
    params: dict,
    content_term: str,
    uid: str,
) -> list[dict]:
    """Combine BM25 (tsvector) and vector similarity for content search."""

    # BM25 via tsvector
    conditions_bm25 = conditions + ["d.full_text_tsv @@ plainto_tsquery('english', :q)"]
    params["q"] = content_term

    join_clause = " ".join(joins)
    where_clause = " AND ".join(conditions_bm25)

    bm25_query = f"""
        SELECT d.id, d.original_filename, d.file_type, d.status, d.doc_type,
               d.domain, d.summary, d.created_at,
               ts_rank(d.full_text_tsv, plainto_tsquery('english', :q)) AS rank,
               (to_tsvector('english', COALESCE(d.user_note, ''))
                @@ plainto_tsquery('english', :q)) AS note_match
        FROM documents d
        {join_clause}
        WHERE {where_clause}
        ORDER BY rank DESC
        LIMIT 30
    """
    bm25_result = await db.execute(text(bm25_query), params)
    bm25_docs: dict[str, dict] = {}
    for row in bm25_result.mappings().fetchall():
        doc = dict(row)
        # Apply +0.3 score boost when the query matches the user_note specifically
        doc["_score"] = float(doc.pop("rank") or 0) + (0.3 if doc.pop("note_match") else 0)
        bm25_docs[str(doc["id"])] = doc

    # Vector similarity search
    try:
        embeddings = await get_embeddings([content_term])
        query_embedding = embeddings[0]
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        vec_query = """
            SELECT c.document_id,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks c
            WHERE c.user_id = :uid
              AND (1 - (c.embedding <=> CAST(:embedding AS vector))) > 0.35
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT 30
        """
        vec_result = await db.execute(
            text(vec_query),
            {"uid": uid, "embedding": embedding_str},
        )
        vec_doc_ids = []
        for row in vec_result.fetchall():
            doc_id = str(row[0])
            if doc_id not in vec_doc_ids:
                vec_doc_ids.append(doc_id)

        # Fetch full doc data for vector results not already in BM25
        missing_ids = [did for did in vec_doc_ids if did not in bm25_docs]
        if missing_ids:
            placeholders = ", ".join(f":vid_{i}" for i in range(len(missing_ids)))
            vid_params = {f"vid_{i}": mid for i, mid in enumerate(missing_ids)}
            vid_params["uid"] = uid
            vec_doc_query = f"""
                SELECT id, original_filename, file_type, status, doc_type,
                       domain, summary, created_at
                FROM documents
                WHERE user_id = :uid AND id IN ({placeholders}) AND deleted_at IS NULL
            """
            vec_doc_result = await db.execute(text(vec_doc_query), vid_params)
            for row in vec_doc_result.mappings().fetchall():
                doc = dict(row)
                doc["_score"] = 0.0  # vector-only; no BM25 rank to boost
                bm25_docs[str(doc["id"])] = doc

    except Exception:
        logger.exception("search.vector_search_failed")

    # Merge: sort by score (BM25 rank + note_match boost) descending, strip internal key
    docs_sorted = sorted(bm25_docs.values(), key=lambda d: d.get("_score", 0), reverse=True)
    for doc in docs_sorted:
        doc.pop("_score", None)

    return docs_sorted[:50]
