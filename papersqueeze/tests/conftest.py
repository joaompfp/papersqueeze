"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from papersqueeze.config.schema import (
    AnthropicConfig,
    AppConfig,
    FieldsConfig,
    PaperlessConfig,
    ProcessingConfig,
    ReviewTagsConfig,
    TagsConfig,
    Template,
    TemplateExtraction,
    TemplateField,
    TemplatesConfig,
    BasePrompts,
    AIModel,
)
from papersqueeze.models.document import Document, CustomFieldValue
from papersqueeze.models.extraction import (
    ClassificationResult,
    ExtractedField,
    ExtractionResult,
    FieldType,
)


@pytest.fixture
def paperless_config() -> PaperlessConfig:
    """Create test paperless config."""
    return PaperlessConfig(
        url="http://localhost:8000/api",
        token="test-token-12345",
        verify_ssl=False,
        timeout_seconds=10,
    )


@pytest.fixture
def anthropic_config() -> AnthropicConfig:
    """Create test anthropic config."""
    return AnthropicConfig(
        api_key="test-api-key",
        gatekeeper_model=AIModel.HAIKU,
        specialist_model=AIModel.SONNET,
        max_tokens=1024,
        timeout_seconds=30,
        max_retries=1,
    )


@pytest.fixture
def tags_config() -> TagsConfig:
    """Create test tags config."""
    return TagsConfig(
        review=ReviewTagsConfig(
            needs_review="ai-review-needed",
            approved="ai-approved",
            rejected="ai-rejected",
            processed="ai-processed",
        ),
    )


@pytest.fixture
def app_config(
    paperless_config: PaperlessConfig,
    anthropic_config: AnthropicConfig,
    tags_config: TagsConfig,
) -> AppConfig:
    """Create test app config."""
    return AppConfig(
        paperless=paperless_config,
        anthropic=anthropic_config,
        tags=tags_config,
        processing=ProcessingConfig(
            confidence_threshold=0.7,
            review_threshold=0.9,
        ),
    )


@pytest.fixture
def sample_template() -> Template:
    """Create a sample template for testing."""
    return Template(
        id="test_template",
        description="Test template",
        document_type="Invoice",
        correspondent_hint="TEST CORP",
        extraction=TemplateExtraction(
            rules="Extract test fields",
            fields=[
                TemplateField(name="issue_date", type="date", required=True),
                TemplateField(name="total_gross", type="amount", required=True),
                TemplateField(name="invoice_number", type="string", required=False),
            ],
        ),
        field_mapping={
            "issue_date": "Issue Date",
            "total_gross": "Total Gross",
            "invoice_number": "Invoice Number",
        },
        title_format="{issue_date} | {invoice_number} | {total_gross} EUR",
        tags_add=["ai-processed"],
    )


@pytest.fixture
def templates_config(sample_template: Template) -> TemplatesConfig:
    """Create test templates config."""
    return TemplatesConfig(
        base_prompts=BasePrompts(
            gatekeeper="Test gatekeeper prompt",
            specialist="Test specialist prompt",
        ),
        templates=[
            sample_template,
            Template(
                id="fallback_general",
                description="Fallback",
                document_type="Invoice",
                extraction=TemplateExtraction(
                    rules="Generic extraction",
                    fields=[
                        TemplateField(name="issue_date", type="date", required=True),
                        TemplateField(name="total_gross", type="amount", required=True),
                    ],
                ),
                field_mapping={
                    "total_gross": "Total Gross",
                },
                title_format="{issue_date} | {total_gross} EUR",
            ),
        ],
    )


@pytest.fixture
def sample_document() -> Document:
    """Create a sample document for testing."""
    return Document(
        id=123,
        title="Test Document",
        content="This is a test invoice from TEST CORP dated 15/01/2025 for 123,45 EUR",
        created="2025-01-15",
        correspondent=1,
        correspondent_name="TEST CORP",
        document_type=1,
        document_type_name="Invoice",
        tags=[1, 2],
        tag_names=["test", "invoice"],
        custom_fields=[
            CustomFieldValue(field=1, field_name="Total Gross", value=None),
            CustomFieldValue(field=2, field_name="Invoice Number", value=None),
        ],
    )


@pytest.fixture
def sample_document_with_values() -> Document:
    """Create a document with existing custom field values."""
    return Document(
        id=456,
        title="Existing Document",
        content="Invoice content",
        created="2025-01-10",
        correspondent=1,
        correspondent_name="EXISTING CORP",
        document_type=1,
        document_type_name="Invoice",
        tags=[1],
        tag_names=["invoice"],
        custom_fields=[
            CustomFieldValue(field=1, field_name="Total Gross", value="100.00"),
            CustomFieldValue(field=2, field_name="Invoice Number", value="INV-001"),
        ],
    )


@pytest.fixture
def sample_classification() -> ClassificationResult:
    """Create a sample classification result."""
    return ClassificationResult(
        template_id="test_template",
        confidence=0.95,
        reasoning="Matched TEST CORP header",
        processing_time_ms=150.0,
    )


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    """Create a sample extraction result."""
    return ExtractionResult(
        template_id="test_template",
        template_confidence=0.95,
        fields={
            "issue_date": ExtractedField(
                name="issue_date",
                raw_value="15/01/2025",
                normalized_value="2025-01-15",
                confidence=0.95,
                field_type=FieldType.DATE,
            ),
            "total_gross": ExtractedField(
                name="total_gross",
                raw_value="123,45",
                normalized_value="123.45",
                confidence=0.90,
                field_type=FieldType.AMOUNT,
            ),
            "invoice_number": ExtractedField(
                name="invoice_number",
                raw_value="INV-2025-001",
                normalized_value="INV-2025-001",
                confidence=0.85,
                field_type=FieldType.STRING,
            ),
        },
        processing_time_ms=2500.0,
    )


@pytest.fixture
def mock_paperless_client() -> AsyncMock:
    """Create a mock paperless client."""
    client = AsyncMock()

    # Setup default returns
    client.get_document = AsyncMock()
    client.patch_document = AsyncMock()
    client.get_tag_by_name = AsyncMock()
    client.add_tag_to_document = AsyncMock()
    client.remove_tag_from_document = AsyncMock()
    client.get_custom_field_by_name = AsyncMock()
    client.get_correspondent_by_name = AsyncMock()
    client.get_document_type_by_name = AsyncMock()

    return client


@pytest.fixture
def mock_claude_client() -> MagicMock:
    """Create a mock claude client."""
    client = MagicMock()
    client.classify_document = MagicMock()
    client.extract_metadata = MagicMock()
    client.classify_and_extract = MagicMock()
    return client
