"""Custom exceptions for PaperSqueeze."""

from typing import Any


class PaperSqueezeError(Exception):
    """Base exception for all PaperSqueeze errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ConfigurationError(PaperSqueezeError):
    """Configuration loading or validation failed."""

    pass


class PaperlessAPIError(PaperSqueezeError):
    """Paperless-ngx API communication error."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(
            message,
            details={
                **(details or {}),
                "status_code": status_code,
                "response_body": response_body,
            },
        )


class PaperlessNotFoundError(PaperlessAPIError):
    """Resource not found in Paperless-ngx."""

    def __init__(self, resource_type: str, identifier: str | int) -> None:
        super().__init__(
            f"{resource_type} not found: {identifier}",
            status_code=404,
            details={"resource_type": resource_type, "identifier": identifier},
        )


class PaperlessAuthError(PaperlessAPIError):
    """Authentication failed with Paperless-ngx."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class ClaudeAPIError(PaperSqueezeError):
    """Anthropic Claude API error."""

    def __init__(
        self,
        message: str,
        error_type: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_type = error_type
        super().__init__(
            message,
            details={**(details or {}), "error_type": error_type},
        )


class ClaudeRateLimitError(ClaudeAPIError):
    """Claude API rate limit exceeded."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after}s" if retry_after else "Rate limit exceeded",
            error_type="rate_limit",
            details={"retry_after": retry_after},
        )


class ExtractionError(PaperSqueezeError):
    """AI extraction failed or returned invalid data."""

    def __init__(
        self,
        message: str,
        template_id: str | None = None,
        raw_response: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.template_id = template_id
        self.raw_response = raw_response
        super().__init__(
            message,
            details={
                **(details or {}),
                "template_id": template_id,
                "raw_response": raw_response,
            },
        )


class ClassificationError(ExtractionError):
    """Document classification failed."""

    pass


class ValidationError(PaperSqueezeError):
    """Data validation failed."""

    def __init__(
        self,
        field: str,
        message: str,
        value: Any = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.field = field
        self.value = value
        super().__init__(
            f"Validation failed for '{field}': {message}",
            details={**(details or {}), "field": field, "value": value},
        )


class ReviewWorkflowError(PaperSqueezeError):
    """Review queue operation failed."""

    def __init__(
        self,
        message: str,
        doc_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.doc_id = doc_id
        super().__init__(
            message,
            details={**(details or {}), "doc_id": doc_id},
        )


class ProcessingError(PaperSqueezeError):
    """Document processing failed."""

    def __init__(
        self,
        message: str,
        doc_id: int | None = None,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.doc_id = doc_id
        self.stage = stage
        super().__init__(
            message,
            details={**(details or {}), "doc_id": doc_id, "stage": stage},
        )
