# 05 — Coding Standards

This file is required reading for every coding session. It defines folder structure, design patterns, and conventions.

## Repository layout

```
/
  web/                         # Next.js frontend
  api/                         # FastAPI + worker
  plan/                        # docs (this folder)
  docker-compose.yml
```

## Frontend folder structure (`/web`)

```
web/
  app/                                  # Next.js App Router pages
    (auth)/
      login/page.tsx
      signup/page.tsx
    (app)/
      layout.tsx                        # authenticated shell
      page.tsx                          # /  → library
      library/page.tsx                  # /library → same as / (deep-link)
      document/[id]/page.tsx
      chat/page.tsx
      graph/page.tsx
      settings/page.tsx
    api/
      documents/route.ts
      folders/route.ts
      tags/route.ts
      graph/route.ts
  components/
    ui/                                 # shadcn/ui copy-ins
    library/                            # document grid, doc card, etc.
    upload/                             # uploader, dropzone, progress
    search/                             # search bar, chips, results
    chat/                               # chat UI, message list, citations
    graph/                              # entity graph view
    pipeline/                           # pipeline animation
    shared/                             # cross-feature: empty states, etc.
  lib/
    supabase/
      client.ts                         # browser client
      server.ts                         # server client (for RSC + route handlers)
      middleware.ts                     # session refresh
    api/                                # client functions calling our BFF
      documents.ts
      folders.ts
      search.ts
      chat.ts
    realtime/
      subscriptions.ts                  # typed channel helpers
    types/                              # shared TS types matching backend Pydantic models
    constants.ts
    utils/                              # small pure utils
      format.ts
      file.ts
      cn.ts
    hooks/
      use-documents.ts
      use-realtime-document.ts
      use-search.ts
  stores/                               # zustand stores
    library.ts
    chat.ts
    upload.ts
  styles/
    globals.css
  middleware.ts                         # Supabase auth middleware
  next.config.ts
  tailwind.config.ts
  tsconfig.json
```

## Backend folder structure (`/api`)

```
api/
  app/
    main.py                             # FastAPI app factory
    config.py                           # typed settings (pydantic-settings)
    deps.py                             # FastAPI dependencies (auth, db, etc.)
    routes/
      __init__.py
      documents.py                      # POST /enqueue, etc.
      search.py
      chat.py
      graph.py
      health.py
    services/                           # business logic, no framework
      __init__.py
      documents/
        ingestion.py                    # raw text/image extraction per file type
        types.py                        # service-level dataclasses
      search/
        resolver.py                     # term → facet
        query.py                        # facet chips → SQL
        vocab_cache.py                  # per-user facet vocabulary cache
      chat/
        retriever.py                    # hybrid retrieval (KG + vectors)
        responder.py                    # streaming Claude call
      knowledge/
        entity_resolver.py              # entity matching logic (deterministic + LLM-assisted)
        fact_versioning.py
      pipeline/
        orchestrator.py                 # the 5-stage pipeline driver
        state_machine.py                # document status transitions
    agents/                             # one file per agent
      __init__.py
      base.py                           # shared types, retry, tracing wrapper
      classifier.py
      schema_architect.py
      extractor.py
      verifier.py
      knowledge_integrator.py
      prompts/                          # markdown prompts loaded at runtime
        classifier.md
        schema_architect.md
        extractor.md
        verifier.md
        knowledge_integrator.md
    repositories/                       # all DB queries; one per aggregate
      __init__.py
      documents_repo.py
      folders_repo.py
      tags_repo.py
      entities_repo.py
      facts_repo.py
      chunks_repo.py
      events_repo.py
    integrations/                       # external service clients
      __init__.py
      anthropic_client.py               # wrapped Anthropic SDK
      openai_embeddings.py
      supabase_client.py                # server-side supabase-py
      langfuse_client.py
    worker/
      __init__.py
      worker.py                         # arq WorkerSettings
      tasks.py                          # job functions
    parsing/                            # file-type-specific parsers
      __init__.py
      pdf.py
      image.py
      docx.py
      pptx.py
      xlsx.py
      csv.py
      txt.py
      router.py                         # MIME → parser
    db/
      __init__.py
      session.py                        # async SQLAlchemy
      models.py                         # ORM models matching migrations
      base.py
    utils/
      hashing.py
      filenames.py
      json_helpers.py
      mime.py
    constants.py
    errors.py                           # typed exception hierarchy
  migrations/
    env.py                              # alembic
    versions/
  tests/
    unit/
    integration/
    fixtures/                           # sample documents for tests
  pyproject.toml
  requirements.txt
  Dockerfile
```

## Naming conventions

- **Files**: `snake_case.py` in Python; `kebab-case.ts` in TS components; `camelCase.ts` for non-component TS modules
- **Classes**: `PascalCase`
- **Functions**: `snake_case` in Python; `camelCase` in TS
- **Constants**: `SCREAMING_SNAKE_CASE` in both
- **DB columns**: `snake_case`, plural for collections
- **API routes**: `/kebab-case`

## Design patterns

### Pattern: Repository
All DB access goes through a repository class. Routes and services never write raw SQL.

```python
# repositories/documents_repo.py
class DocumentsRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: UUID, dto: DocumentCreate) -> Document: ...
    async def get(self, user_id: UUID, doc_id: UUID) -> Document | None: ...
    async def update_status(self, doc_id: UUID, status: DocumentStatus) -> None: ...
    async def list_by_user(self, user_id: UUID, filters: DocumentFilters) -> list[Document]: ...
```

### Pattern: Service
Business logic. Services orchestrate repositories and integrations. No framework imports here.

```python
# services/documents/ingestion.py
class IngestionService:
    def __init__(self, docs_repo: DocumentsRepo, parser_router: ParserRouter): ...
    async def extract_raw(self, doc: Document) -> RawExtraction: ...
```

### Pattern: Agent
Each agent is a class with a single `run(input)` method, wrapped with tracing and retries.

```python
# agents/base.py
class Agent(Generic[TIn, TOut]):
    name: str
    model: str

    async def run(self, input: TIn, trace_id: str | None = None) -> TOut:
        # wraps: load prompt, call LLM, validate output, emit trace
        ...
```

### Pattern: Pipeline orchestrator
The 5-stage pipeline is a state machine. Stages are pure functions of (document, previous outputs). Persisted between stages so failures resume from the last good stage.

```python
# services/pipeline/orchestrator.py
class PipelineOrchestrator:
    async def run(self, doc_id: UUID) -> None:
        doc = await self.docs_repo.get_by_id(doc_id)
        while doc.status != 'ready' and doc.status != 'failed':
            doc = await self._run_next_stage(doc)
```

### Pattern: BFF route (Next.js)
Next.js API routes are thin. Parse body → call FastAPI or Supabase → return.

```ts
// app/api/documents/route.ts
export async function POST(req: Request) {
  const body = DocumentCreateSchema.parse(await req.json())
  const supabase = createServerClient(...)
  const { data: user } = await supabase.auth.getUser()
  // ... call supabase to create row + call FastAPI /enqueue
  return Response.json({ doc_id })
}
```

### Pattern: Typed config
One place for env vars, validated at boot.

```python
# config.py
class Settings(BaseSettings):
    database_url: PostgresDsn
    anthropic_api_key: SecretStr
    ...
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()  # raises if anything missing
```

### Pattern: Error hierarchy
```python
# errors.py
class AppError(Exception): ...
class NotFoundError(AppError): ...
class ValidationError(AppError): ...
class ExternalServiceError(AppError): ...
class AgentExtractionError(AppError): ...
```

Route handlers convert these to HTTP via a single exception handler.

## When to put code where (the test)

Ask: "Where would I look for this if I came back in 6 months?"
- If the answer is "where files become text" → `parsing/`
- "where we save a document" → `repositories/documents_repo.py`
- "where the pipeline decides what to do next" → `services/pipeline/orchestrator.py`
- "where we ask Claude to classify" → `agents/classifier.py`
- "where we know what `wife` means" → `services/knowledge/entity_resolver.py`
- "where the UI calls the API" → `lib/api/`

If the answer is unclear, the function is in the wrong place — split or move.

## Function sizing rules

- A function does **one** thing. If you need a comma in the description ("...and..."), split it.
- Max 50 lines per function. If you exceed, extract helpers.
- Max 4 positional arguments. More → use a dataclass/Pydantic model.
- No nesting deeper than 3 levels of control flow. Extract or use early returns.

## Error handling pattern

**Backend:**
```python
try:
    result = await service.do_thing(input)
except NotFoundError as e:
    logger.info("not_found", extra={"input": input.model_dump()})
    raise HTTPException(404, str(e))
except ExternalServiceError as e:
    logger.exception("external_failure")
    raise HTTPException(502, "Upstream service failed")
except Exception:
    logger.exception("unexpected_error")
    raise HTTPException(500, "Internal error")
```

**Worker:** Wrap job in tracer + structured logger. On failure, set `documents.status = 'failed'` and `failure_reason` then re-raise so arq retries.

**Frontend:** Errors surface as toasts via a `useError()` hook. Never console.error and swallow.

## Logging standards

- Use `structlog` in Python with JSON output in production. Each log line includes `user_id`, `document_id` if applicable, `trace_id`.
- Never log raw document content, file contents, full prompts, or API keys.
- Levels: DEBUG (verbose dev only), INFO (lifecycle), WARNING (recoverable), ERROR (caller likely affected), CRITICAL (down).

## Testing standards

Phase 1 minimum:
- One unit test per agent (mocked LLM, asserts prompt structure)
- One integration test per pipeline stage (real DB, real Redis, mocked LLM)
- One e2e happy-path test (upload → ready) with a fixture PDF
- RLS test: spawn two users, verify A cannot read B's documents

`pytest -q` must pass before any merge to `main`.

## Lint / format / type

Run before every commit:
```bash
# /api
ruff check . && ruff format . && mypy app/

# /web
pnpm lint && pnpm typecheck
```

A pre-commit hook is set up in Day 1 to enforce.

## Commits

Conventional Commits. Examples:
- `feat(upload): support docx parsing`
- `fix(verifier): retry only flagged fields`
- `chore(deps): pin sqlalchemy 2.0.30`
- `docs(progress): close day-2-be-04`

One logical change per commit. Long commit message body if the why isn't obvious from the subject.
