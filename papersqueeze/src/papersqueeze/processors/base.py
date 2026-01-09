"""Base processor class for document type handling."""

from abc import ABC, abstractmethod
from typing import Any

from papersqueeze.config.schema import Template
from papersqueeze.models.document import Document
from papersqueeze.models.extraction import ExtractedField, ExtractionResult, FieldType
from papersqueeze.utils.formatting import format_ledger_title
from papersqueeze.utils.normalization import (
    normalize_amount,
    normalize_date,
    normalize_number,
    normalize_text,
)


class BaseProcessor(ABC):
    """Abstract base class for document type processors.

    Each processor handles a specific document type (invoices, tax docs, etc.)
    and knows how to normalize extracted data and format titles.
    """

    @property
    @abstractmethod
    def template_id(self) -> str:
        """Unique identifier for this processor's template."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of document type."""
        ...

    def normalize_field(self, field: ExtractedField) -> ExtractedField:
        """Normalize a single extracted field based on its type.

        Args:
            field: Field to normalize.

        Returns:
            Field with normalized_value populated.
        """
        if field.raw_value is None:
            return field

        normalized: str | None = None

        match field.field_type:
            case FieldType.DATE:
                normalized = normalize_date(field.raw_value)
            case FieldType.AMOUNT:
                normalized = normalize_amount(field.raw_value)
            case FieldType.NUMBER:
                normalized = normalize_number(field.raw_value)
            case FieldType.INTEGER:
                num = normalize_number(field.raw_value)
                if num:
                    try:
                        normalized = str(int(float(num)))
                    except ValueError:
                        normalized = num
            case FieldType.STRING:
                normalized = normalize_text(field.raw_value)
            case _:
                normalized = normalize_text(field.raw_value)

        field.normalized_value = normalized
        return field

    def normalize_extraction(self, extraction: ExtractionResult) -> ExtractionResult:
        """Normalize all fields in an extraction result.

        Args:
            extraction: Extraction result with raw values.

        Returns:
            Extraction result with normalized values.
        """
        for field_name, field in extraction.fields.items():
            self.normalize_field(field)

        return extraction

    def format_title(
        self,
        template: Template,
        extraction: ExtractionResult,
        document: Document | None = None,
    ) -> str:
        """Format document title using template format string.

        Args:
            template: Template with title format.
            extraction: Extraction result with field values.
            document: Optional document for fallback values.

        Returns:
            Formatted title string.
        """
        # Build values dict from extraction
        values: dict[str, Any] = {}

        for field_name, field in extraction.fields.items():
            value = field.normalized_value or field.raw_value
            if value:
                values[field_name] = value

        # Add document date as fallback
        if "issue_date" not in values and document and document.created:
            values["issue_date"] = document.created.isoformat()

        return format_ledger_title(template.title_format, values)

    def validate_extraction(
        self,
        extraction: ExtractionResult,
        template: Template,
    ) -> list[str]:
        """Validate extraction against template requirements.

        Args:
            extraction: Extraction result to validate.
            template: Template with field requirements.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        # Check required fields
        required_fields = [f.name for f in template.extraction.fields if f.required]

        for field_name in required_fields:
            field = extraction.fields.get(field_name)
            if not field or not field.has_value:
                errors.append(f"Required field '{field_name}' is missing")
            elif field.confidence < 0.5:
                errors.append(
                    f"Required field '{field_name}' has low confidence ({field.confidence:.2f})"
                )

        return errors

    def post_process(
        self,
        extraction: ExtractionResult,
        document: Document,
    ) -> ExtractionResult:
        """Apply any post-processing specific to this document type.

        Override in subclasses for custom logic.

        Args:
            extraction: Normalized extraction result.
            document: Source document.

        Returns:
            Post-processed extraction result.
        """
        return extraction

    def get_tags_to_add(self, template: Template) -> list[str]:
        """Get tags that should be added to document.

        Args:
            template: Template configuration.

        Returns:
            List of tag names to add.
        """
        return template.tags_add

    def get_tags_to_suggest(self, template: Template) -> list[str]:
        """Get tags that should be suggested (for review).

        Args:
            template: Template configuration.

        Returns:
            List of tag names to suggest.
        """
        return template.tags_suggest

    def get_document_type(self, template: Template) -> str | None:
        """Get document type to assign.

        Args:
            template: Template configuration.

        Returns:
            Document type name, or None.
        """
        return template.document_type

    def get_correspondent_hint(self, template: Template) -> str | None:
        """Get correspondent hint for matching.

        Args:
            template: Template configuration.

        Returns:
            Correspondent name hint, or None.
        """
        return template.correspondent_hint
