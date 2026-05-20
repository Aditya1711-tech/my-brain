class AppError(Exception):
    """Base error for all application errors."""

    def __init__(self, message: str = "An application error occurred") -> None:
        self.message = message
        super().__init__(self.message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, resource: str = "Resource", identifier: str = "") -> None:
        detail = f"{resource} not found"
        if identifier:
            detail = f"{resource} '{identifier}' not found"
        super().__init__(detail)


class ValidationError(AppError):
    """Invalid input or state."""


class ExternalServiceError(AppError):
    """Upstream service (LLM, storage, etc.) failed."""


class AgentExtractionError(AppError):
    """Agent could not extract or validate data."""


class DuplicateError(AppError):
    """Duplicate resource (e.g., same file hash for user)."""
