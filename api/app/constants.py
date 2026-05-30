# LLM model identifiers — do not change without updating KNOWLEDGE.md
MODEL_CLASSIFIER = "claude-haiku-4-5-20251001"
MODEL_SCHEMA_ARCHITECT = "claude-sonnet-4-6"
MODEL_EXTRACTOR = "claude-sonnet-4-6"
MODEL_VERIFIER = "claude-haiku-4-5-20251001"
MODEL_KNOWLEDGE_INTEGRATOR = "claude-sonnet-4-6"
MODEL_SUMMARIZER = "claude-haiku-4-5-20251001"
MODEL_CHAT = "claude-sonnet-4-6"
MODEL_EMBEDDINGS = "text-embedding-3-small"

EMBEDDING_DIMENSIONS = 1536

# Pipeline
MAX_RETRY_COUNT = 2

# File types (normalized)
ALLOWED_FILE_TYPES = frozenset({"pdf", "image", "docx", "xlsx", "pptx", "csv", "txt"})

ALLOWED_MIME_TYPES = frozenset({
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/csv",
    "text/plain",
})
