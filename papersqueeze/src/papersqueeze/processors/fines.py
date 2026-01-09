"""Law enforcement fines processor."""

from papersqueeze.config.schema import Template
from papersqueeze.models.document import Document
from papersqueeze.models.extraction import ExtractedField, ExtractionResult, FieldType
from papersqueeze.processors.base import BaseProcessor
from papersqueeze.utils.normalization import calculate_due_date


class FinesProcessor(BaseProcessor):
    """Processor for traffic fines and law enforcement documents (ANSR, etc.).

    These documents typically have strict payment deadlines and
    should be marked as high priority.
    """

    @property
    def template_id(self) -> str:
        return "law_enforcement_fines"

    @property
    def description(self) -> str:
        return "Traffic fines (ANSR). High priority."

    def post_process(
        self,
        extraction: ExtractionResult,
        document: Document,
    ) -> ExtractionResult:
        """Post-process fine extraction.

        - Auto-calculate due date (typically 15 days from issue)
        - Extract license plate if present
        """
        # Calculate due date if we have issue_date
        if "issue_date" in extraction.fields and extraction.fields["issue_date"].has_value:
            issue_date = extraction.fields["issue_date"].normalized_value
            if issue_date:
                due_date = calculate_due_date(issue_date, days=15)
                if due_date:
                    # Add or update due_date field
                    if "due_date" not in extraction.fields:
                        extraction.fields["due_date"] = ExtractedField(
                            name="due_date",
                            raw_value=None,
                            normalized_value=due_date,
                            confidence=0.9,  # Calculated, not extracted
                            field_type=FieldType.DATE,
                            extraction_notes="Auto-calculated: 15 days from issue date",
                        )
                    elif not extraction.fields["due_date"].has_value:
                        extraction.fields["due_date"].normalized_value = due_date
                        extraction.fields["due_date"].confidence = 0.9

        # Try to extract plate number from content if not already extracted
        if "plate" not in extraction.fields or not extraction.fields["plate"].has_value:
            plate = self._extract_plate(document.content)
            if plate:
                if "plate" not in extraction.fields:
                    extraction.fields["plate"] = ExtractedField(
                        name="plate",
                        raw_value=plate,
                        normalized_value=plate,
                        confidence=0.8,
                        field_type=FieldType.STRING,
                    )
                else:
                    extraction.fields["plate"].normalized_value = plate

        return extraction

    def _extract_plate(self, content: str) -> str | None:
        """Extract Portuguese license plate from content.

        Portuguese plates follow patterns like:
        - XX-XX-XX (old format)
        - XX-XX-00 (newer format with numbers)
        - AA-00-AA (current format since 2020)

        Args:
            content: Document text content.

        Returns:
            Extracted plate or None.
        """
        import re

        # Common Portuguese plate patterns
        patterns = [
            r"\b([A-Z]{2}[-\s]?[A-Z]{2}[-\s]?[A-Z]{2})\b",  # XX-XX-XX
            r"\b([A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{2})\b",     # AA-00-AA (current)
            r"\b(\d{2}[-\s]?[A-Z]{2}[-\s]?\d{2})\b",       # 00-XX-00
            r"\b([A-Z]{2}[-\s]?\d{2}[-\s]?\d{2})\b",       # XX-00-00
        ]

        content_upper = content.upper()

        for pattern in patterns:
            match = re.search(pattern, content_upper)
            if match:
                plate = match.group(1)
                # Normalize format: XX-XX-XX
                plate = re.sub(r"[\s]", "-", plate)
                if "-" not in plate and len(plate) == 6:
                    plate = f"{plate[:2]}-{plate[2:4]}-{plate[4:]}"
                return plate

        return None

    def get_tags_to_add(self, template: Template) -> list[str]:
        """Get tags to add - fines are high priority."""
        base_tags = super().get_tags_to_add(template)
        # Ensure priority tagging (if your system uses it)
        return base_tags
