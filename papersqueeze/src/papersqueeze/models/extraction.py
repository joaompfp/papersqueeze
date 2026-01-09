"""AI extraction result models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldType(str, Enum):
    """Supported field types for extraction."""

    STRING = "string"
    DATE = "date"
    AMOUNT = "amount"
    NUMBER = "number"
    INTEGER = "integer"


@dataclass
class ExtractedField:
    """A single field extracted by AI."""

    name: str
    raw_value: str | None
    normalized_value: str | None = None
    confidence: float = 0.0
    field_type: FieldType = FieldType.STRING
    extraction_notes: str | None = None

    def __post_init__(self) -> None:
        """Ensure confidence is in valid range."""
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_confident(self) -> bool:
        """Check if extraction has high confidence (>0.7)."""
        return self.confidence >= 0.7

    @property
    def has_value(self) -> bool:
        """Check if field has a usable value."""
        return self.normalized_value is not None or self.raw_value is not None

    @property
    def best_value(self) -> str | None:
        """Get the best available value (normalized preferred)."""
        return self.normalized_value or self.raw_value


@dataclass
class ClassificationResult:
    """Result of document classification by gatekeeper AI."""

    template_id: str
    confidence: float
    reasoning: str | None = None
    processing_time_ms: float = 0.0
    raw_response: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure confidence is in valid range."""
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_confident(self) -> bool:
        """Check if classification has high confidence (>0.8)."""
        return self.confidence >= 0.8


@dataclass
class ExtractionResult:
    """Result of data extraction by specialist AI."""

    template_id: str
    template_confidence: float
    fields: dict[str, ExtractedField]
    raw_response: dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0
    extraction_notes: str | None = None

    def __post_init__(self) -> None:
        """Ensure confidence is in valid range."""
        self.template_confidence = max(0.0, min(1.0, self.template_confidence))

    def get_field(self, name: str) -> ExtractedField | None:
        """Get extracted field by name."""
        return self.fields.get(name)

    def get_field_value(self, name: str) -> str | None:
        """Get the best value for a field by name."""
        field = self.fields.get(name)
        return field.best_value if field else None

    def get_field_confidence(self, name: str) -> float:
        """Get confidence for a specific field."""
        field = self.fields.get(name)
        return field.confidence if field else 0.0

    @property
    def overall_confidence(self) -> float:
        """Calculate overall extraction confidence.

        Average of template confidence and mean field confidence.
        """
        if not self.fields:
            return self.template_confidence

        field_confidences = [f.confidence for f in self.fields.values() if f.has_value]
        if not field_confidences:
            return self.template_confidence

        mean_field_confidence = sum(field_confidences) / len(field_confidences)
        return (self.template_confidence + mean_field_confidence) / 2

    @property
    def confident_fields(self) -> dict[str, ExtractedField]:
        """Get only fields with high confidence."""
        return {
            name: field
            for name, field in self.fields.items()
            if field.is_confident and field.has_value
        }

    @property
    def field_names(self) -> list[str]:
        """Get list of all extracted field names."""
        return list(self.fields.keys())

    @property
    def extracted_count(self) -> int:
        """Count of fields with values."""
        return sum(1 for f in self.fields.values() if f.has_value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "template_id": self.template_id,
            "template_confidence": self.template_confidence,
            "overall_confidence": self.overall_confidence,
            "fields": {
                name: {
                    "raw_value": field.raw_value,
                    "normalized_value": field.normalized_value,
                    "confidence": field.confidence,
                    "type": field.field_type.value,
                }
                for name, field in self.fields.items()
            },
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass
class ProposedChange:
    """A proposed change to a document field."""

    field_name: str
    current_value: Any
    proposed_value: Any
    confidence: float
    source: str = "ai"  # "ai" or "rule"
    reason: str | None = None

    @property
    def is_fill(self) -> bool:
        """Check if this fills an empty field."""
        return self.current_value is None or self.current_value == ""

    @property
    def is_change(self) -> bool:
        """Check if this changes an existing value."""
        return not self.is_fill and self.current_value != self.proposed_value


@dataclass
class ProcessingResult:
    """Result of processing a document."""

    doc_id: int
    success: bool
    template_id: str | None = None
    classification: ClassificationResult | None = None
    extraction: ExtractionResult | None = None
    proposed_changes: list[ProposedChange] = field(default_factory=list)
    applied_changes: list[ProposedChange] = field(default_factory=list)
    review_required: bool = False
    error_message: str | None = None
    processing_time_ms: float = 0.0

    @property
    def changes_count(self) -> int:
        """Count of proposed changes."""
        return len(self.proposed_changes)

    @property
    def applied_count(self) -> int:
        """Count of applied changes."""
        return len(self.applied_changes)

    @property
    def needs_review(self) -> bool:
        """Check if document needs human review."""
        return self.review_required or any(
            change.is_change and change.confidence < 0.9
            for change in self.proposed_changes
        )
