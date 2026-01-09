"""Tax document processor."""

from papersqueeze.models.document import Document
from papersqueeze.models.extraction import ExtractionResult
from papersqueeze.processors.base import BaseProcessor


class TaxProcessor(BaseProcessor):
    """Processor for Portuguese tax authority (AT) documents.

    Handles IRS, DMR, IUC, and other tax-related documents.
    """

    @property
    def template_id(self) -> str:
        return "tax_at_guides"

    @property
    def description(self) -> str:
        return "Tax Authority documents (IRS, DMR, IUC)"

    def post_process(
        self,
        extraction: ExtractionResult,
        document: Document,
    ) -> ExtractionResult:
        """Post-process tax document extraction.

        - Normalize tax period format (YYYY/MM)
        - Identify tax type from content
        """
        # Try to identify tax type if not extracted
        if "tax_type" not in extraction.fields or not extraction.fields["tax_type"].has_value:
            tax_type = self._detect_tax_type(document.content)
            if tax_type and "tax_type" in extraction.fields:
                extraction.fields["tax_type"].normalized_value = tax_type
                extraction.fields["tax_type"].confidence = 0.7

        return extraction

    def _detect_tax_type(self, content: str) -> str | None:
        """Detect tax type from document content.

        Args:
            content: Document text content.

        Returns:
            Tax type identifier or None.
        """
        content_lower = content.lower()

        # Check for common tax document types
        if "dmr" in content_lower or "declaração mensal" in content_lower:
            return "DMR"
        if "iuc" in content_lower or "imposto único de circulação" in content_lower:
            return "IUC"
        if "irs" in content_lower or "imposto sobre o rendimento" in content_lower:
            return "IRS"
        if "imt" in content_lower or "imposto municipal sobre transmissões" in content_lower:
            return "IMT"
        if "imi" in content_lower or "imposto municipal sobre imóveis" in content_lower:
            return "IMI"
        if "iva" in content_lower or "imposto sobre o valor acrescentado" in content_lower:
            return "IVA"

        return None
