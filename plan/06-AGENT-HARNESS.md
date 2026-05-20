# 06 — Agent Harness

The harness is the core of Phase 1. Read this file before touching `/api/app/agents/` or `/api/app/services/pipeline/`.

## Architecture summary

5 agents + 1 deterministic step, orchestrated by `PipelineOrchestrator`. Each agent:
- Has a single responsibility
- Takes typed input, returns typed output
- Uses Anthropic tool-use for structured output
- Is wrapped in tracing (Langfuse)
- Persists output before next agent runs (checkpoints)

```
[Document] → text/image extraction (deterministic)
          → 1. Classifier (Haiku)
          → 2. Schema Architect (Sonnet)
          → 3. Extractor (Sonnet, multimodal)
          → 4. Verifier (Haiku)  ⟲ retry low-confidence fields (max 2 retries)
          → 5. Knowledge Integrator (Sonnet)
          → Vectorization (deterministic)
          → Ready
```

## Shared base class

```python
# agents/base.py
from typing import Generic, TypeVar
from pydantic import BaseModel

TIn = TypeVar("TIn", bound=BaseModel)
TOut = TypeVar("TOut", bound=BaseModel)

class Agent(Generic[TIn, TOut]):
    name: str = ""                  # e.g., "classifier"
    model: str = ""                 # e.g., "claude-haiku-4-5-20251001"
    prompt_path: str = ""           # relative path under agents/prompts/
    output_schema: type[BaseModel]  # the Pydantic class for tool output

    async def run(self, input: TIn, *, trace_id: str | None = None) -> TOut:
        prompt = self._load_prompt(input)
        with self._trace(trace_id):
            raw = await anthropic_client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=[self._tool_definition()],
                tool_choice={"type": "tool", "name": self.output_schema.__name__},
                messages=[{"role": "user", "content": prompt}],
            )
            tool_use = self._extract_tool_use(raw)
            return self.output_schema.model_validate(tool_use.input)
```

Validation is automatic — if the model returns bad JSON, Pydantic raises. Caller decides whether to retry.

## Agent 1: Classifier

**Model:** Haiku 4.5
**Input:** Raw extracted text (first 2 pages) + first-page image (if available)
**Output:** `ClassifierOutput`

```python
class ClassifierOutput(BaseModel):
    document_type: str          # specific snake_case (passport, marriage_certificate, x_ray_report, ppt_q4_strategy)
    domain: Literal['personal','medical','legal','financial','professional','educational','other']
    country: str | None         # ISO-3166 alpha-2 or null
    primary_language: str       # ISO-639-1
    is_scanned: bool
    is_handwritten: bool
    is_digital: bool
    has_clear_text: bool
    entity_hints: list[EntityHint]  # what entities seem to be mentioned

class EntityHint(BaseModel):
    name: str
    type: str                   # person | organization | asset | other
    role: Literal['subject','author','mentioned','witness','other']
```

**Prompt** (`agents/prompts/classifier.md`):

```
You are a document classifier. Examine the provided document text and image.

Return a precise classification using the tool. Be specific:
- "marriage_certificate" not "certificate"
- "x_ray_report" not "medical_document"
- "ppt_q4_strategy" not "presentation"

If genuinely unclear, use "unknown_<best_guess>" (e.g., "unknown_form").

For document_type, use lowercase snake_case.

For entity_hints, list names of people/orgs/assets clearly mentioned in the document, with their apparent role:
- subject: the document is about them (e.g., passport holder)
- author: they issued/wrote it (e.g., issuing authority on cert)
- mentioned: appears in body
- witness: signed as witness
- other: anything else

Quality signals are best-effort. If you can't tell, default to false for is_scanned and is_handwritten.

For domain:
- personal: identity docs, family, household
- medical: patient records, reports, scans
- legal: contracts, court docs, legal notices
- financial: statements, invoices, tax docs
- professional: work artifacts, business docs
- educational: certs, transcripts, learning materials
- other: anything else
```

## Agent 2: Schema Architect

**Model:** Sonnet 4.6
**Input:** Classifier output + document text sample
**Output:** `SchemaOutput`

```python
class SchemaField(BaseModel):
    name: str
    field_type: Literal['string','number','date','enum','identifier','currency_amount','boolean']
    description: str
    required: bool
    is_entity_field: bool       # true if this field is a person/org name
    enum_values: list[str] | None = None

class SchemaOutput(BaseModel):
    document_type: str          # echoed from classifier
    fields: list[SchemaField]
    entity_extraction_required: bool   # true if document is about a person/org/asset
    notes: str | None           # any architect notes for extractor
```

**Prompt** (`agents/prompts/schema_architect.md`):

```
You are a schema architect. Given a document classification, design the extraction schema.

For KNOWN document types, follow standard templates:
- passport: holder_name, passport_number, dob, gender, nationality, place_of_birth, issue_date, expiry_date, issuing_authority
- birth_certificate: child_name, dob, place_of_birth, father_name, mother_name, registration_number, issue_date
- marriage_certificate: spouse_1_name, spouse_2_name, marriage_date, place_of_marriage, registration_number
- driving_license: holder_name, license_number, dob, address, issue_date, expiry_date, vehicle_classes
- pan_card: holder_name, pan_number, dob, father_name (India)
- aadhaar: holder_name, aadhaar_number (last 4), dob, gender, address (India)
- x_ray_report: patient_name, patient_id, scan_date, body_part, findings, conclusion, radiologist
- invoice: vendor_name, invoice_number, invoice_date, total_amount, line_items_summary, customer_name
- ppt_*: title, presenter, date, key_topics, action_items, audience

For UNKNOWN types, design a reasonable schema:
- Always include a title/subject field
- Always include date(s) if any time reference appears
- Always extract entity names (people/orgs/assets) with their role
- Include 3-8 fields that capture the document's substantive content
- Mark essential fields as required=true

For fields involving people, set is_entity_field=true.
For identifiers (numbers like passport_number, PAN, ISIN), set field_type=identifier.

Keep field names snake_case. Field count: 3-12. Don't pad with trivial fields.
```

## Agent 3: Extractor

**Model:** Sonnet 4.6 (multimodal)
**Input:** Schema + document text + page images (for images and image-heavy PDFs)
**Output:** `ExtractionOutput`

```python
class ExtractedField(BaseModel):
    name: str
    value: str | None           # null if not present
    raw_value: str | None       # before any normalization
    source_location: str | None # "page 2", "footer", etc.

class ExtractionOutput(BaseModel):
    fields: list[ExtractedField]
    detected_entities: list[ExtractedEntity]

class ExtractedEntity(BaseModel):
    name: str
    type: str
    role: str
    fields: dict[str, str]      # any attrs extracted (dob, address, etc.)
```

**Prompt** (`agents/prompts/extractor.md`):

```
You are a document data extractor. Extract structured fields from the document.

CRITICAL RULES:
- Extract LITERAL values from the document. Do not infer, guess, or compute.
- If a required field is not visible, set value to null. Do not invent.
- Preserve original formatting for identifiers (passport numbers, PAN, etc.) — do not normalize case or spacing.
- For dates, return ISO 8601 (YYYY-MM-DD) if you can determine the format with confidence; otherwise return raw text.
- For currency, separate the number and the currency code if visible.
- For people's names, return them exactly as written. Don't reorder first/last.

For each extracted entity (person, organization, asset):
- Provide canonical name
- Provide the role (subject, author, mentioned, witness, beneficiary, other)
- Provide any additional attributes you can extract (dob, address, etc.)

Use multimodal capability — read what you see in the page images if text extraction missed anything.
```

**Retry on verifier flags:** When called for a retry, the prompt is augmented:

```
This is a RETRY for specific fields that previous extraction got wrong.
Fields to re-examine: {field_names}
Verifier feedback: {reasoning_per_field}

Focus only on these fields. Look more carefully at the image. Consider alternative interpretations.
Return values for ALL schema fields, but pay particular attention to the flagged ones.
```

## Agent 4: Verifier

**Model:** Haiku 4.5
**Input:** Schema + extracted fields + document text (and image if needed)
**Output:** `VerificationOutput`

```python
class FieldVerification(BaseModel):
    field_name: str
    confidence: float           # 0.0–1.0
    needs_retry: bool
    reasoning: str

class VerificationOutput(BaseModel):
    fields: list[FieldVerification]
    overall_quality: float      # 0.0–1.0
```

**Prompt** (`agents/prompts/verifier.md`):

```
You are an extraction verifier. For each extracted field, score confidence 0.0–1.0 and flag for retry if confidence < 0.7.

Confidence rubric:
- 1.0: value matches the document exactly, no ambiguity
- 0.8–0.99: value looks correct, minor format question
- 0.5–0.79: plausible but uncertain — flag for retry
- < 0.5: likely wrong, missing, or hallucinated — flag for retry

Set needs_retry=true if:
- Required field is empty but the document plausibly contains it
- Value contradicts the document
- Format is wrong (e.g., a number where a date should be)
- Identifier looks malformed (e.g., wrong length for passport)

In reasoning, be brief: "matches doc text exactly" / "doc says X, extracted Y" / "field empty but doc has 'dob: 15/05/1990'".

Set overall_quality based on how complete and confident the extraction is.
```

**Retry policy:**
- If any field has `needs_retry=true` and `retry_count < 2`: re-run Extractor with only those fields flagged.
- After retry, re-run Verifier. If any field still fails after 2 retries, accept the value with low confidence and surface it in the UI.

## Agent 5: Knowledge Integrator

**Model:** Sonnet 4.6
**Input:** Detected entities + extracted facts + existing entities for this user
**Output:** `IntegrationOutput`

```python
class EntityResolution(BaseModel):
    detected_name: str
    detected_type: str
    decision: Literal['match_existing','create_new','uncertain']
    matched_entity_id: str | None
    new_canonical_name: str | None
    aliases_to_add: list[str]
    reasoning: str

class FactToWrite(BaseModel):
    entity_id_placeholder: str  # references EntityResolution; resolved before DB write
    field_name: str
    field_value: str
    field_type: str
    confidence: float

class RelationshipToWrite(BaseModel):
    from_entity_placeholder: str
    to_entity_placeholder: str
    relation_type: str

class IntegrationOutput(BaseModel):
    resolutions: list[EntityResolution]
    facts: list[FactToWrite]
    relationships: list[RelationshipToWrite]
```

**Prompt** (`agents/prompts/knowledge_integrator.md`):

```
You are a knowledge integrator. Given detected entities from a new document and existing entities in this user's knowledge graph, decide for each detected entity whether it matches an existing one or is new.

Matching rules (in priority order):
1. Hard identifier match: same passport_number, same PAN, same ISIN, same employee_id — these are definitive.
2. Same full name + same DOB → match.
3. Strong name similarity + shared family relationships → match (e.g., variant spellings).
4. Name similarity but no other signal → mark uncertain. Do NOT auto-merge.

For matched entities, list any new aliases to add (e.g., new spelling variant, nickname).
For new entities, provide canonical_name and aliases.

For facts (passport_number, dob, salary, expiry_date, etc.) detected on each entity:
- Always emit fact rows, regardless of match decision
- entity_id_placeholder references the EntityResolution that resolved this entity

For relationships (spouse_of, child_of, parent_of, patient_of, etc.) you can infer from the document:
- Marriage cert → spouse_of bi-directional between the two parties
- Birth cert → child_of (child → father), child_of (child → mother), parent_of (parents → child)
- Other relationships: only if explicit in the document

Do NOT speculate. Only emit relationships clearly stated.

Output rules:
- For every detected entity, emit exactly one EntityResolution
- Facts and relationships reference entities by their resolution's placeholder (the detected_name)
```

## Vectorization (deterministic, not an agent)

After integration, run:
1. Build a representative text per document: `summary + extracted_field_name:value pairs + raw_text (chunked)`.
2. Chunk to ~512-token windows with 64-token overlap.
3. Call OpenAI embeddings API (batch up to 100 inputs).
4. Insert rows into `chunks` table.

No LLM reasoning here. Pure pipeline.

## Tracing

Every agent call wrapped in a Langfuse trace:
- Trace per document: `trace_id = document_id`
- Span per agent: `name = agent.name`, with `input` and `output` attached
- Token usage attached as metadata
- Errors surface as failed spans with stack trace

Langfuse UI then shows the full tree for any document — exactly what to demo.

## Cost guardrails

Target: ≤ $0.10 per document avg.
- Classifier (Haiku, ~2k tokens in, ~500 out): ~$0.002
- Schema architect (Sonnet, ~3k in, ~1k out): ~$0.015
- Extractor (Sonnet, ~5k in + 1 image, ~2k out): ~$0.025
- Verifier (Haiku, ~3k in, ~1k out): ~$0.002
- Knowledge integrator (Sonnet, ~3k in, ~1k out): ~$0.012
- Embeddings (OpenAI 3-small): negligible
- Retry headroom: ~$0.04

If actual cost trends higher in dev, add cost logging to `agents/base.py` and surface in PROGRESS.md as a blocker.

## Failure modes and handling

| Failure | Action |
|---------|--------|
| LLM API timeout | Retry with backoff (max 3). On final failure, set document status `failed`. |
| Tool output fails Pydantic validation | Retry once with error message appended. Then fail document. |
| Extractor returns empty for required field after 2 retries | Accept with confidence=0.0 in DB. Mark for UI review. |
| Entity resolution returns `uncertain` | Create as new entity with metadata flag `needs_review=true`. Surface in UI. |
| OCR fails on a scanned PDF | Fall back to multimodal LLM on the page image. |
| Embeddings API fails | Pipeline completes without vectors; document is searchable via BM25 only. Mark for re-embedding. |

## Local dev tip

Add a `--replay <doc_id>` flag to the worker CLI that re-runs the pipeline from any stage. This is how you iterate on prompts without re-uploading.
