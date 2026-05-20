# 01 — Project Overview

## What we're building

**Project Brain** — a personal intelligence layer that lets a user upload anything (documents, images, files of any common type) and automatically extracts structured knowledge from each upload using a five-agent AI harness. Users can then search, filter, chat with single documents, and (via the knowledge graph) get instant answers to factual questions about their own content.

The system is **domain-agnostic** from day one: personal users store identity documents, doctors store patient files, professionals store work artifacts. The harness adapts the extraction schema to whatever document type appears.

## Phase 1 scope (this build)

In scope for the 5-day Phase 1:

1. **Auth + multi-tenant data isolation** — Supabase Auth + Row-Level Security
2. **Document upload** — file goes to object storage, record goes to DB; supports PDF, image, docx, xlsx, xls, pptx, csv, txt
3. **Folders** — users can organize uploads into a Drive-like folder tree
4. **Tags** — many-to-many between documents and tags; users create and reuse
5. **Five-agent harness** — classifier → schema architect → extractor → verifier → knowledge integrator. Plus deterministic vectorization. Runs async in workers.
6. **Knowledge graph** — entities (person, asset, project, etc.) + facts (versioned over time) + relationships
7. **Search + filter** — chip-based composing filters across file type, folder, tag, doc type, entity, date, content
8. **Single-document chat** — NotebookLM-style chat scoped to a selected document
9. **Cross-document chat** — knowledge-graph-grounded answers to factual queries
10. **Tracing** — Langfuse instrumentation across the harness
11. **Live progress UI** — Supabase Realtime drives the per-document pipeline animation

Explicitly **out of scope** for Phase 1:

- Video and audio processing (defer to Phase 1.5)
- Financial intelligence layer (Phase 2)
- Sharing / collaboration
- Mobile app (web-responsive only)
- OAuth providers other than Supabase's built-in
- "Smart merge" UI for ambiguous entity resolution (just flag and ask user)
- Re-running extraction at scale (single doc re-run is fine)

## Demo target (end of day 5)

The 3-minute demo should land these moments, in order:

1. **Upload moment** — drag-and-drop 4–5 mixed-type files (a passport scan, a marriage certificate, a medical report, a PPT, an invoice). Show the document grid populate instantly.
2. **Pipeline moment** — zoom into one document; show the five agents tick through live (classify → schema → extract → verify → integrate) via Realtime updates.
3. **Knowledge moment** — open the knowledge graph view; show entities and relationships auto-built (spouse, child relationships from family certs; project/client from work docs).
4. **Search moment** — type "pdf" → Enter → "passport" → Enter → "wife" → Enter; show three chips composing into a precise single-result hit ("wife → Priya's passport"). This is THE moment.
5. **Chat moment** — open chat with all-documents scope; ask "when does my passport expire?" → cited answer from the knowledge layer. Then ask the same against a single document.
6. **Tracing moment** — open Langfuse, show the full trace tree for one document showing five agent calls with their inputs/outputs.

## Success criteria

- Upload 10 different document types and have 9 of 10 extract correctly with at least one meaningful field per document
- End-to-end pipeline (upload → searchable) completes in ≤ 90 seconds per document
- Cost per document ≤ $0.10 with the model split defined in `06-AGENT-HARNESS.md`
- Search resolves common queries in ≤ 100 ms
- Zero cross-user data leaks (verified by RLS tests)
- The Langfuse trace tree is visually impressive

## Phase 2 preview (do NOT build now)

Phase 2 extends this base with: financial document intelligence (CAS, salary slips, CC bills, insurance policies), net-worth dashboard, portfolio overlap analysis, tax position tracking, goal-based planning. The Phase 1 entity + fact model is intentionally designed to absorb this without rework.
