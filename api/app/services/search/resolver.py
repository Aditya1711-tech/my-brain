"""Search resolver — turns search terms into structured facet chips."""

import json
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import MODEL_CLASSIFIER
from app.integrations.anthropic_client import create_message
from app.services.search.vocab_cache import VocabCache

logger = structlog.get_logger()


class SearchChip:
    """A resolved search facet chip."""

    def __init__(self, facet: str, value: str, display: str) -> None:
        self.facet = facet
        self.value = value
        self.display = display

    def to_dict(self) -> dict:
        return {"facet": self.facet, "value": self.value, "display": self.display}


class SearchResolver:
    def __init__(self, db: AsyncSession, user_id: UUID) -> None:
        self.db = db
        self.user_id = user_id
        self.vocab = VocabCache(db, user_id)

    async def resolve(self, term: str) -> SearchChip:
        """Resolve a search term into a facet chip.

        Tiered approach:
        1. Exact/case-insensitive match against vocabulary
        2. Trigram fuzzy match
        3. Haiku LLM call to parse ambiguous term into structured filter
        """
        await self.vocab.load()

        # Tier 1: Exact match
        match = self.vocab.exact_match(term)
        if match:
            logger.info("search.resolve_exact", term=term, facet=match["facet"])
            return SearchChip(**match)

        # Tier 2: Trigram fuzzy match
        fuzzy = await self._fuzzy_match(term)
        if fuzzy:
            logger.info("search.resolve_fuzzy", term=term, facet=fuzzy["facet"])
            return SearchChip(**fuzzy)

        # Tier 3: LLM call to parse ambiguous term
        llm_result = await self._llm_resolve(term)
        if llm_result:
            logger.info("search.resolve_llm", term=term, facet=llm_result["facet"])
            return SearchChip(**llm_result)

        # Final fallback: free-text content search
        logger.info("search.resolve_content", term=term)
        return SearchChip(facet="content", value=term, display=term)

    async def _fuzzy_match(self, term: str) -> dict | None:
        """Try trigram similarity match against entities, doc types, folders, tags, domains."""
        uid = str(self.user_id)

        # Entity name fuzzy match
        result = await self.db.execute(
            text("""
                SELECT id, canonical_name, similarity(canonical_name, :term) AS sim
                FROM entities
                WHERE user_id = :uid AND similarity(canonical_name, :term) > 0.3
                ORDER BY sim DESC
                LIMIT 1
            """),
            {"uid": uid, "term": term},
        )
        row = result.fetchone()
        if row:
            return {
                "facet": "entity",
                "value": str(row[0]),
                "display": row[1],
            }

        # Doc type fuzzy match
        result = await self.db.execute(
            text("""
                SELECT DISTINCT doc_type, similarity(doc_type, :term) AS sim
                FROM documents
                WHERE user_id = :uid AND doc_type IS NOT NULL
                  AND similarity(doc_type, :term) > 0.3
                  AND deleted_at IS NULL
                ORDER BY sim DESC
                LIMIT 1
            """),
            {"uid": uid, "term": term},
        )
        row = result.fetchone()
        if row:
            return {
                "facet": "doc_type",
                "value": row[0],
                "display": row[0].replace("_", " "),
            }

        # Folder name fuzzy match
        result = await self.db.execute(
            text("""
                SELECT id, name, similarity(name, :term) AS sim
                FROM folders
                WHERE user_id = :uid AND similarity(name, :term) > 0.3
                ORDER BY sim DESC
                LIMIT 1
            """),
            {"uid": uid, "term": term},
        )
        row = result.fetchone()
        if row:
            return {
                "facet": "folder",
                "value": str(row[0]),
                "display": row[1],
            }

        # Tag name fuzzy match
        result = await self.db.execute(
            text("""
                SELECT id, name, similarity(name, :term) AS sim
                FROM tags
                WHERE user_id = :uid AND similarity(name, :term) > 0.3
                ORDER BY sim DESC
                LIMIT 1
            """),
            {"uid": uid, "term": term},
        )
        row = result.fetchone()
        if row:
            return {
                "facet": "tag",
                "value": str(row[0]),
                "display": row[1],
            }

        # Domain fuzzy match
        result = await self.db.execute(
            text("""
                SELECT DISTINCT domain, similarity(domain, :term) AS sim
                FROM documents
                WHERE user_id = :uid AND domain IS NOT NULL
                  AND similarity(domain, :term) > 0.3
                  AND deleted_at IS NULL
                ORDER BY sim DESC
                LIMIT 1
            """),
            {"uid": uid, "term": term},
        )
        row = result.fetchone()
        if row:
            return {
                "facet": "domain",
                "value": row[0],
                "display": row[0],
            }

        return None

    async def _llm_resolve(self, term: str) -> dict | None:
        """Tier 3: Use Haiku to parse an ambiguous term into a structured filter."""
        available_facets = {
            "file_type": sorted(self.vocab.file_types),
            "doc_type": sorted(self.vocab.doc_types),
            "domain": sorted(self.vocab.domains),
            "entity": sorted(self.vocab.entity_names.keys()),
            "folder": sorted(self.vocab.folder_names.keys()),
            "tag": sorted(self.vocab.tag_names.keys()),
        }

        # Only call LLM if there are facets to match against
        total_values = sum(len(v) for v in available_facets.values())
        if total_values == 0:
            return None

        prompt = (
            "You are a search query parser. The user typed a search term and we need to "
            "resolve it to a structured facet filter.\n\n"
            f"Search term: \"{term}\"\n\n"
            f"Available facets and values:\n{json.dumps(available_facets, indent=2)}\n\n"
            "Return a JSON object with exactly these keys:\n"
            '- "facet": one of file_type, doc_type, domain, entity, folder, tag, or "content" if none match\n'
            '- "value": the matched value from the available values, or the original term for content\n'
            '- "display": human-readable display text\n\n'
            "If the term clearly matches a facet value (even with typos or partial match), use that facet. "
            "If genuinely ambiguous or no match, use content facet.\n"
            "Return ONLY the JSON object, no explanation."
        )

        try:
            response = await create_message(
                model=MODEL_CLASSIFIER,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            # Parse JSON from response (handle potential markdown wrapping)
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)

            facet = parsed.get("facet", "content")
            value = parsed.get("value", term)
            display = parsed.get("display", term)

            # Validate: resolve entity names to IDs
            if facet == "entity":
                entity_id = self.vocab.entity_names.get(value.lower())
                if entity_id:
                    return {"facet": "entity", "value": entity_id, "display": display}
                return None
            elif facet == "folder":
                folder_id = self.vocab.folder_names.get(value.lower())
                if folder_id:
                    return {"facet": "folder", "value": folder_id, "display": display}
                return None
            elif facet == "tag":
                tag_id = self.vocab.tag_names.get(value.lower())
                if tag_id:
                    return {"facet": "tag", "value": tag_id, "display": display}
                return None
            elif facet in ("file_type", "doc_type", "domain"):
                return {"facet": facet, "value": value, "display": display}

            return None

        except Exception:
            logger.exception("search.llm_resolve_failed", term=term)
            return None
