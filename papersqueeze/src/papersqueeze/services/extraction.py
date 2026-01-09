"""Extraction service - convenience wrapper around Claude client."""

from papersqueeze.api.claude import ClaudeClient
from papersqueeze.config.schema import TemplatesConfig
from papersqueeze.models.extraction import ClassificationResult, ExtractionResult


class ExtractionService:
    """Service for AI-powered document extraction.

    This is a thin wrapper around ClaudeClient that provides
    a cleaner interface for the processor.
    """

    def __init__(self, claude: ClaudeClient, templates: TemplatesConfig) -> None:
        """Initialize extraction service.

        Args:
            claude: Claude API client.
            templates: Templates configuration.
        """
        self.claude = claude
        self.templates = templates

    def classify(self, content: str) -> ClassificationResult:
        """Classify a document to determine its type.

        Args:
            content: Document OCR text content.

        Returns:
            ClassificationResult with template ID and confidence.
        """
        return self.claude.classify_document(content, self.templates)

    def extract(self, content: str, template_id: str) -> ExtractionResult:
        """Extract metadata from a document.

        Args:
            content: Document OCR text content.
            template_id: Template ID to use for extraction.

        Returns:
            ExtractionResult with extracted fields.
        """
        template = self.templates.get_template_by_id(template_id)
        if not template:
            template = self.templates.get_template_by_id("fallback_general")
            if not template:
                raise ValueError(f"Template not found: {template_id}")

        return self.claude.extract_metadata(
            content=content,
            template=template,
            base_specialist_prompt=self.templates.base_prompts.specialist,
        )

    def classify_and_extract(
        self, content: str
    ) -> tuple[ClassificationResult, ExtractionResult]:
        """Classify and extract in one call.

        Args:
            content: Document OCR text content.

        Returns:
            Tuple of (ClassificationResult, ExtractionResult).
        """
        return self.claude.classify_and_extract(content, self.templates)
