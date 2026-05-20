"""Document status transitions. Only valid transitions are allowed."""

# Mapping from current status → set of valid next statuses
_TRANSITIONS: dict[str, set[str]] = {
    "uploaded": {"extracting_text", "failed"},
    "extracting_text": {"classified", "failed"},
    "classified": {"schema_built", "failed"},
    "schema_built": {"extracted", "failed"},
    "extracted": {"verified", "failed"},
    "verified": {"extracted", "integrated", "failed"},  # verified → extracted for retry
    "integrated": {"vectorized", "failed"},
    "vectorized": {"ready", "failed"},
    "ready": set(),
    "failed": {"uploaded"},  # allow re-enqueue from failed
}

# Which stage runs for each status transition
STATUS_TO_STAGE: dict[str, str] = {
    "uploaded": "text_extraction",
    "extracting_text": "classification",
    "classified": "schema_building",
    "schema_built": "extraction",
    "extracted": "verification",
    "verified": "integration",
    "integrated": "vectorization",
}


def can_transition(current: str, target: str) -> bool:
    """Check if a status transition is valid."""
    return target in _TRANSITIONS.get(current, set())


def next_status_after(current: str) -> str | None:
    """Get the default next status in the happy path."""
    happy_path = [
        "uploaded",
        "extracting_text",
        "classified",
        "schema_built",
        "extracted",
        "verified",
        "integrated",
        "vectorized",
        "ready",
    ]
    try:
        idx = happy_path.index(current)
        return happy_path[idx + 1] if idx + 1 < len(happy_path) else None
    except ValueError:
        return None
