"""Entity resolution — pre-filter candidates via SQL, then let KI agent decide."""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_integrator import (
    IntegrationOutput,
    KnowledgeIntegratorAgent,
    KnowledgeIntegratorInput,
)
from app.repositories.entities_repo import EntitiesRepo
from app.repositories.facts_repo import FactsRepo

logger = structlog.get_logger()


class EntityResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.entities_repo = EntitiesRepo(db)
        self.facts_repo = FactsRepo(db)

    async def resolve_and_persist(
        self,
        user_id: UUID,
        document_id: UUID,
        document_type: str,
        detected_entities: list[dict],
        extracted_fields: list[dict],
        trace_id: str,
        user_note: str | None = None,
    ) -> IntegrationOutput:
        """Run entity resolution: pre-filter candidates, call KI agent, persist results."""

        # Step 1: Collect names, identifiers, and DOB from detected entities
        names = [e["name"] for e in detected_entities if e.get("name")]
        identifiers: dict[str, str] = {}
        dob: str | None = None
        for entity in detected_entities:
            for key, value in entity.get("fields", {}).items():
                if key in (
                    "passport_number", "pan", "pan_number", "aadhaar_number",
                    "isin", "employee_id", "license_number", "registration_number",
                ):
                    identifiers[key] = value
                elif key in ("date_of_birth", "dob", "birth_date") and not dob:
                    dob = value

        # Step 2: Pre-filter candidates from DB via trigram + phonetic + identifier + DOB
        candidates = await self.entities_repo.find_candidates(user_id, names, identifiers, dob=dob)

        # Serialize candidates for the LLM (relationships + known_dob filled below)
        existing_entities = []
        for c in candidates:
            existing_entities.append({
                "id": str(c["id"]),
                "entity_type": c["entity_type"],
                "canonical_name": c["canonical_name"],
                "aliases": c["aliases"] if isinstance(c["aliases"], list) else [],
                "identifiers": c["identifiers"] if isinstance(c["identifiers"], dict) else {},
                "linked_doc_types": list(c["linked_doc_types"]) if c.get("linked_doc_types") else [],
                "relationships": [],
                "known_dob": None,
            })

        # Batch-fetch relationships and known DOBs (one query each, not N)
        if existing_entities:
            candidate_ids = [ent["id"] for ent in existing_entities]
            id_ph = ", ".join(f":cid_{i}" for i in range(len(candidate_ids)))
            id_params: dict = {f"cid_{i}": cid for i, cid in enumerate(candidate_ids)}

            rel_result = await self.db.execute(
                text(f"""
                    SELECT from_entity_id::text, to_entity_id::text, relation_type
                    FROM entity_relationships
                    WHERE user_id = :user_id
                      AND (from_entity_id::text IN ({id_ph}) OR to_entity_id::text IN ({id_ph}))
                """),
                {"user_id": str(user_id), **id_params},
            )
            rel_map: dict[str, list[dict]] = {cid: [] for cid in candidate_ids}
            for row in rel_result.fetchall():
                from_id, to_id, rel_type = row[0], row[1], row[2]
                if from_id in rel_map:
                    rel_map[from_id].append({"relation_type": rel_type, "with_entity_id": to_id})
                if to_id in rel_map:
                    rel_map[to_id].append({"relation_type": rel_type, "with_entity_id": from_id})

            dob_result = await self.db.execute(
                text(f"""
                    SELECT entity_id::text, field_value
                    FROM facts
                    WHERE user_id = :user_id
                      AND entity_id::text IN ({id_ph})
                      AND field_name = 'date_of_birth'
                      AND valid_until IS NULL
                """),
                {"user_id": str(user_id), **id_params},
            )
            dob_map = {row[0]: row[1] for row in dob_result.fetchall()}

            for ent in existing_entities:
                eid = ent["id"]
                ent["relationships"] = rel_map.get(eid, [])
                ent["known_dob"] = dob_map.get(eid)

        logger.info(
            "entity_resolver.candidates",
            doc_id=str(document_id),
            detected_count=len(detected_entities),
            candidate_count=len(existing_entities),
        )

        # Step 3: Call Knowledge Integrator agent
        ki_input = KnowledgeIntegratorInput(
            document_type=document_type,
            detected_entities=detected_entities,
            extracted_fields=extracted_fields,
            existing_entities=existing_entities,
        )
        output = await KnowledgeIntegratorAgent().run(ki_input, trace_id=trace_id)

        # Step 4: Persist resolutions — build entity ID map
        entity_id_map: dict[str, str] = {}  # detected_name → actual entity UUID

        for res in output.resolutions:
            if res.decision == "match_existing" and res.matched_entity_id:
                entity_id_map[res.detected_name] = res.matched_entity_id
                # Add new aliases
                if res.aliases_to_add:
                    await self.entities_repo.add_aliases(
                        res.matched_entity_id, res.aliases_to_add
                    )
                # Merge identifiers from detected entity
                detected = next(
                    (e for e in detected_entities if e["name"] == res.detected_name), None
                )
                if detected and detected.get("fields"):
                    ident_fields = {
                        k: v for k, v in detected["fields"].items()
                        if k in identifiers
                    }
                    if ident_fields:
                        await self.entities_repo.update_identifiers(
                            res.matched_entity_id, ident_fields
                        )
            else:
                # create_new or uncertain — create a new entity
                detected = next(
                    (e for e in detected_entities if e["name"] == res.detected_name), None
                )
                canonical = res.new_canonical_name or res.detected_name
                entity_type = res.detected_type or (detected["type"] if detected else "other")
                aliases = res.aliases_to_add or []

                # Extract identifiers from the detected entity's fields
                ident = {}
                if detected and detected.get("fields"):
                    ident = {
                        k: v for k, v in detected["fields"].items()
                        if k in (
                            "passport_number", "pan", "pan_number", "aadhaar_number",
                            "isin", "employee_id", "license_number", "registration_number",
                        )
                    }

                new_id = await self.entities_repo.create(
                    user_id=user_id,
                    entity_type=entity_type,
                    canonical_name=canonical,
                    aliases=aliases,
                    identifiers=ident,
                )
                entity_id_map[res.detected_name] = new_id

            # Link entity to document
            detected = next(
                (e for e in detected_entities if e["name"] == res.detected_name), None
            )
            role = detected["role"] if detected and detected.get("role") else "mentioned"
            entity_id = entity_id_map.get(res.detected_name)
            if entity_id:
                await self.entities_repo.link_document(
                    document_id=document_id,
                    entity_id=entity_id,
                    user_id=user_id,
                    role=role,
                )

        # Step 5: Persist facts
        for fact in output.facts:
            entity_id = entity_id_map.get(fact.entity_id_placeholder)
            if not entity_id:
                logger.warning(
                    "entity_resolver.fact_no_entity",
                    placeholder=fact.entity_id_placeholder,
                )
                continue
            await self.facts_repo.upsert(
                user_id=user_id,
                entity_id=entity_id,
                source_document_id=document_id,
                field_name=fact.field_name,
                field_value=fact.field_value,
                field_type=fact.field_type,
                confidence=fact.confidence,
            )

        # Step 6: Persist relationships
        for rel in output.relationships:
            from_id = entity_id_map.get(rel.from_entity_placeholder)
            to_id = entity_id_map.get(rel.to_entity_placeholder)
            if not from_id or not to_id:
                logger.warning(
                    "entity_resolver.relationship_no_entity",
                    from_placeholder=rel.from_entity_placeholder,
                    to_placeholder=rel.to_entity_placeholder,
                )
                continue
            await self.entities_repo.create_relationship(
                user_id=user_id,
                from_entity_id=from_id,
                to_entity_id=to_id,
                relation_type=rel.relation_type,
            )

        await self.db.commit()

        logger.info(
            "entity_resolver.complete",
            doc_id=str(document_id),
            entities_resolved=len(output.resolutions),
            facts_written=len(output.facts),
            relationships_written=len(output.relationships),
        )

        return output
