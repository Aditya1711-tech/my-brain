"""#tag parser and storage for user note text."""

import json
import re
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Match #tag tokens: not preceded by a word char, # followed by a letter then word chars.
# This excludes purely numeric tags (#123) and nested hashes (##) from doubling.
_TAG_RE = re.compile(r'(?<!\w)#([a-zA-Z]\w*)')


def parse_tags(text_content: str) -> list[str]:
    """Extract #tag tokens from note text.

    Returns lowercase tag names (without #), deduplicated, in order of first appearance.
    """
    if not text_content:
        return []
    seen: set[str] = set()
    tags: list[str] = []
    for match in _TAG_RE.finditer(text_content):
        tag = match.group(1).lower()
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


async def store_tags(
    db: AsyncSession,
    document_id: UUID,
    user_id: UUID,
    tags: list[str],
) -> None:
    """Merge new tags into documents.metadata['tags'] with set semantics.

    Existing tags are preserved; new ones appended. Result is sorted for stable storage.
    Idempotent: re-running with the same tags produces the same state.
    """
    if not tags:
        return

    await db.execute(
        text("""
            UPDATE documents
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{tags}',
                (
                    SELECT COALESCE(jsonb_agg(val ORDER BY val), '[]'::jsonb)
                    FROM (
                        SELECT jsonb_array_elements_text(
                            COALESCE(metadata->'tags', '[]'::jsonb)
                        ) AS val
                        UNION
                        SELECT jsonb_array_elements_text(CAST(:new_tags AS jsonb))
                    ) combined
                )
            )
            WHERE id = :doc_id AND user_id = :user_id
        """),
        {
            "doc_id": str(document_id),
            "user_id": str(user_id),
            "new_tags": json.dumps(tags),
        },
    )
    await db.commit()

    logger.info(
        "tag_parser.tags_stored",
        document_id=str(document_id),
        count=len(tags),
        tags=tags,
    )
