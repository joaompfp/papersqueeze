"""Pydantic models for configuration validation."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class PaperlessConfig(BaseModel):
    """Paperless-ngx connection configuration."""

    url: str = Field(
        default="http://localhost:8000/api",
        description="Paperless-ngx API base URL",
    )
    token: str = Field(description="API authentication token")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")
    timeout_seconds: int = Field(default=30, ge=5, le=300)

    @field_validator("url")
    @classmethod
    def normalize_url(cls, v: str) -> str:
        """Remove trailing slash from URL."""
        return v.rstrip("/")


class LLMConfig(BaseModel):
    """LLM provider configuration (model-agnostic)."""

    provider: str = Field(default="anthropic", description="LLM provider: anthropic, openai, gemini, ollama")
    api_key: str = Field(default="", description="API key for the LLM provider")
    gatekeeper_model: str = Field(default="claude-haiku-4-5-20250514")
    specialist_model: str = Field(default="claude-sonnet-4-20250514")
    vision_model: str = Field(default="claude-sonnet-4-20250514")
    max_tokens: int = Field(default=1024, ge=100, le=8192)
    timeout_seconds: int = Field(default=60, ge=10, le=300)


class ReviewTagsConfig(BaseModel):
    """Tags used for the review workflow."""

    needs_review: str = Field(default="ai-review-needed")
    approved: str = Field(default="ai-approved")
    rejected: str = Field(default="ai-rejected")
    processed: str = Field(default="ai-processed")


class TagsConfig(BaseModel):
    """All tag configurations."""

    review: ReviewTagsConfig = Field(default_factory=ReviewTagsConfig)
    # Category tags are user-defined in templates, not hardcoded


class FieldMappingConfig(BaseModel):
    """Maps semantic field keys to Paperless-ngx custom field names.

    This allows templates to use semantic keys (like 'total_gross')
    which resolve to actual Paperless field names (like 'amt_primary').
    """

    # Financial
    total_gross: str = Field(default="amt_primary")
    total_net: str | None = Field(default="gen_total_net")
    total_vat: str | None = Field(default="gen_total_vat")

    # Identifiers
    invoice_number: str | None = Field(default="gen_number")
    nif: str | None = Field(default="gen_supplier_nif")
    contract_ref: str | None = Field(default="gen_contract_ref")

    # Payment
    mb_entity: str | None = Field(default="pay_mb_entity")
    mb_ref: str | None = Field(default="pay_mb_ref")
    mb_ref_full: str | None = Field(default="pay_ref")

    # Dates
    issue_date: str | None = Field(default="gen_issue_date")
    due_date: str | None = Field(default="pay_due_date")
    period: str | None = Field(default="gen_period")

    # Metrics
    consumption: str | None = Field(default="gen_consumption")
    ref_extra: str | None = Field(default="gen_ref_extra")

    # Description
    short_desc: str | None = Field(default="gen_description")

    def get_paperless_field(self, semantic_key: str) -> str | None:
        """Get the Paperless field name for a semantic key."""
        return getattr(self, semantic_key, None)

    def to_dict(self) -> dict[str, str | None]:
        """Return all mappings as a dict."""
        return self.model_dump()


class ProcessingConfig(BaseModel):
    """Processing behavior configuration."""

    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    review_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    max_content_length: int = Field(default=25000, ge=1000, le=100000)
    dry_run: bool = Field(default=False)


class AppConfig(BaseModel):
    """Root application configuration."""

    paperless: PaperlessConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tags: TagsConfig = Field(default_factory=TagsConfig)
    fields: FieldMappingConfig = Field(default_factory=FieldMappingConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    log_level: LogLevel = Field(default=LogLevel.INFO)

    model_config = {"extra": "forbid"}


# =============================================================================
# Templates Schema
# =============================================================================

class TemplateField(BaseModel):
    """Field definition within a template."""

    name: str
    type: str = Field(default="string")  # string, date, amount, number, integer
    required: bool = Field(default=False)
    description: str | None = Field(default=None)


class TemplateExtraction(BaseModel):
    """Extraction rules for a template."""

    rules: str = Field(description="Extraction rules/instructions")
    fields: list[TemplateField] = Field(default_factory=list)


class Template(BaseModel):
    """Document processing template."""

    id: str = Field(description="Unique template identifier")
    description: str = Field(description="Human-readable description")

    # Selectors for template matching
    correspondent_hint: str | None = Field(default=None)
    correspondent_ids: list[int] = Field(default_factory=list)
    document_type: str | None = Field(default=None)
    document_type_ids: list[int] = Field(default_factory=list)
    content_regex: str | None = Field(default=None)

    # Extraction
    extraction: TemplateExtraction | None = Field(default=None)

    # Field mapping: extracted field name -> Paperless field name
    field_mapping: dict[str, str] = Field(default_factory=dict)

    # Output
    title_format: str | None = Field(default=None)
    tags_add: list[str] = Field(default_factory=list)
    tags_suggest: list[str] = Field(default_factory=list)
    auto_due_date_days: int | None = Field(default=None)

    # Commit policy
    auto_commit: bool = Field(default=False, description="Remove from inbox automatically")
    min_confidence: float = Field(default=0.7)


class BasePrompts(BaseModel):
    """Base prompts for AI operations."""

    gatekeeper: str = Field(default="", description="System prompt for document classification")
    specialist: str = Field(default="", description="System prompt for data extraction")


class TemplatesConfig(BaseModel):
    """Templates configuration file schema."""

    defaults: dict[str, Any] = Field(default_factory=dict)
    base_prompts: BasePrompts = Field(default_factory=BasePrompts)
    templates: list[Template] = Field(default_factory=list)

    def get_template_by_id(self, template_id: str) -> Template | None:
        """Find template by ID."""
        for template in self.templates:
            if template.id == template_id:
                return template
        return None

    def get_template_ids(self) -> list[str]:
        """Get list of all template IDs."""
        return [t.id for t in self.templates]

    def find_template_for_correspondent(self, correspondent_id: int | None, correspondent_name: str | None) -> Template | None:
        """Find template matching a correspondent."""
        if correspondent_id:
            for t in self.templates:
                if correspondent_id in t.correspondent_ids:
                    return t
        if correspondent_name:
            name_lower = correspondent_name.lower()
            for t in self.templates:
                if t.correspondent_hint and t.correspondent_hint.lower() in name_lower:
                    return t
        return None
