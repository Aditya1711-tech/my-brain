# 02 — Tech Stack

All versions pinned. Do not upgrade without recording the decision in `KNOWLEDGE.md`.

## Frontend (`/web`)

| Tech | Version | Purpose |
|------|---------|---------|
| Next.js | 15.x (App Router) | React framework |
| React | 19.x | UI |
| TypeScript | 5.x | Type system |
| Tailwind CSS | 3.4.x | Styling |
| shadcn/ui | latest | Component library (copy-in) |
| lucide-react | latest | Icons |
| @supabase/ssr | latest | Supabase client (SSR-ready) |
| @tanstack/react-query | 5.x | Data fetching + cache |
| zustand | 5.x | Client state |
| react-hook-form + zod | latest | Forms + validation |
| recharts | latest | Charts (used lightly in Phase 1) |
| react-dropzone | latest | File upload UI |

## Backend (`/api`)

| Tech | Version | Purpose |
|------|---------|---------|
| Python | 3.11 | Runtime |
| FastAPI | latest stable | Web framework |
| Pydantic | 2.x | Validation + LLM tool schemas |
| SQLAlchemy | 2.x (async) | ORM |
| asyncpg | latest | Postgres async driver |
| arq | latest | Redis job queue |
| anthropic | latest | Claude SDK |
| openai | latest | Embeddings (via OpenAI) |
| pdfplumber | latest | PDF text + tables |
| pymupdf (fitz) | latest | PDF fallback + image render |
| pikepdf | latest | PDF password unlock |
| python-pptx | latest | PPTX parsing |
| openpyxl | latest | XLSX parsing |
| python-docx | latest | DOCX parsing |
| Pillow | latest | Image handling |
| pytesseract | latest | OCR fallback |
| supabase-py | latest | Supabase server-side ops |
| langfuse | latest | Tracing |
| pytest + pytest-asyncio | latest | Tests |
| ruff + black + mypy | latest | Lint/format/type |

## Data + Infra

| Service | Notes |
|---------|-------|
| Supabase | Auth + Postgres + Storage + Realtime |
| Postgres extensions | `pgvector` (vectors), `pg_trgm` (fuzzy search), `unaccent` (search) |
| Redis | arq queue. Use Upstash free tier for hosted, or Docker locally |
| Langfuse | Self-hosted via Docker Compose for development; managed for production |

## LLM models (do not change without recording)

| Agent | Model | Reason |
|-------|-------|--------|
| Classifier | `claude-haiku-4-5-20251001` | Fast, cheap, sufficient for classification |
| Schema architect | `claude-sonnet-4-6` | Needs reasoning to design schemas |
| Extractor | `claude-sonnet-4-6` | Multimodal + structured tool output |
| Verifier | `claude-haiku-4-5-20251001` | Per-field confidence check |
| Knowledge integrator | `claude-sonnet-4-6` | Entity resolution requires reasoning |
| Chat | `claude-sonnet-4-6` | Quality matters here |
| Embeddings | `text-embedding-3-small` (OpenAI) | Cheap, good enough; 1536-dim |

## Deployment

| Layer | Target |
|-------|--------|
| Frontend | Vercel |
| Backend (FastAPI) | Railway |
| Worker (arq) | Railway (separate service, same project) |
| Redis | Railway plugin OR Upstash |
| Postgres + Storage + Auth | Supabase cloud |
| Langfuse | Railway (development) |

## Environment variables

`.env.example` template (Phase 1):

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Backend
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
BACKEND_API_KEY=     # shared secret between Next.js and FastAPI

# LLM
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Storage
SUPABASE_STORAGE_BUCKET=user-uploads

# Tracing
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=

# App
APP_ENV=development     # development | staging | production
APP_FRONTEND_URL=http://localhost:3000
APP_API_URL=http://localhost:8000
```

## Setup commands (run once on day 1)

```bash
# Web
cd web && pnpm install && pnpm dev

# API
cd api && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Worker (separate terminal)
cd api && source .venv/bin/activate
arq app.worker.WorkerSettings

# Redis (Docker)
docker run -d --name brain-redis -p 6379:6379 redis:7-alpine

# Langfuse (Docker Compose)
git clone https://github.com/langfuse/langfuse.git && cd langfuse && docker compose up -d
```

## Repository structure

Monorepo (single repo, two top-level folders):

```
/
  web/             # Next.js
  api/             # FastAPI + worker
  plan/            # this folder
  .github/
  docker-compose.yml   # local dev (redis, langfuse)
  README.md
```
