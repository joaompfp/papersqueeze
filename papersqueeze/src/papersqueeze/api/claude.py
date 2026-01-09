"""Claude API client using official Anthropic SDK."""

import json
import re
import time
from typing import Any

import anthropic
import structlog

from papersqueeze.config.schema import AnthropicConfig, Template, TemplatesConfig
from papersqueeze.exceptions import (
    ClassificationError,
    ClaudeAPIError,
    ClaudeRateLimitError,
    ExtractionError,
)
from papersqueeze.models.extraction import (
    ClassificationResult,
    ExtractedField,
    ExtractionResult,
    FieldType,
)

logger = structlog.get_logger()

# Regex to extract JSON from markdown code blocks
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
# Fallback: find JSON object in response
JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


def _extract_json_from_response(text: str) -> dict[str, Any]:
    """Extract JSON from AI response that may contain markdown or extra text.

    Args:
        text: Raw AI response text.

    Returns:
        Parsed JSON dictionary.

    Raises:
        ValueError: If no valid JSON found.
    """
    # Try markdown code block first
    match = JSON_BLOCK_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    match = JSON_OBJECT_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try parsing the whole thing
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not extract JSON from response: {e}") from e


class ClaudeClient:
    """Claude API client for document classification and extraction."""

    def __init__(self, config: AnthropicConfig) -> None:
        """Initialize the Claude client.

        Args:
            config: Anthropic API configuration.
        """
        self.config = config
        self.client = anthropic.Anthropic(
            api_key=config.api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def _call_claude(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
    ) -> tuple[str, float]:
        """Make a call to Claude API.

        Args:
            model: Model ID to use.
            system_prompt: System prompt for context.
            user_message: User message (document content).
            max_tokens: Override default max tokens.

        Returns:
            Tuple of (response text, processing time in ms).

        Raises:
            ClaudeRateLimitError: If rate limited.
            ClaudeAPIError: On other API errors.
        """
        start_time = time.perf_counter()

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens or self.config.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Extract text from response
            if response.content and len(response.content) > 0:
                text = response.content[0].text
                return text, elapsed_ms

            raise ClaudeAPIError("Empty response from Claude", error_type="empty_response")

        except anthropic.RateLimitError as e:
            raise ClaudeRateLimitError() from e
        except anthropic.APIError as e:
            raise ClaudeAPIError(
                f"Claude API error: {e}",
                error_type=type(e).__name__,
            ) from e

    def classify_document(
        self,
        content: str,
        templates_config: TemplatesConfig,
    ) -> ClassificationResult:
        """Classify a document to determine which template to use.

        Uses the gatekeeper model (fast, cheap) to classify the document.

        Args:
            content: Document OCR text content.
            templates_config: Templates configuration with prompts and template list.

        Returns:
            ClassificationResult with selected template ID and confidence.

        Raises:
            ClassificationError: If classification fails.
        """
        log = logger.bind(operation="classify")

        # Build the classification prompt
        template_descriptions = "\n".join(
            f"- {t.id}: {t.description}"
            for t in templates_config.templates
        )

        system_prompt = templates_config.base_prompts.gatekeeper
        user_message = f"""Available templates:
{template_descriptions}

Document content (truncated):
{content[:self.config.max_tokens * 3]}

Classify this document and return JSON with:
- template_id: The ID of the best matching template
- confidence: Your confidence (0.0 to 1.0)
- reasoning: Brief explanation (optional)
"""

        try:
            response_text, elapsed_ms = self._call_claude(
                model=self.config.gatekeeper_model.value,
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=256,  # Classification needs minimal tokens
            )

            log.debug("Classification response", response=response_text[:200])

            # Parse response
            try:
                data = _extract_json_from_response(response_text)
            except ValueError as e:
                raise ClassificationError(
                    f"Failed to parse classification response: {e}",
                    raw_response=response_text,
                ) from e

            template_id = data.get("template_id") or data.get("selected_id")
            if not template_id:
                raise ClassificationError(
                    "No template_id in classification response",
                    raw_response=response_text,
                )

            # Validate template exists
            valid_ids = templates_config.get_template_ids()
            if template_id not in valid_ids:
                log.warning(
                    "Unknown template ID, using fallback",
                    returned_id=template_id,
                    valid_ids=valid_ids,
                )
                template_id = "fallback_general"

            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning")

            result = ClassificationResult(
                template_id=template_id,
                confidence=confidence,
                reasoning=reasoning,
                processing_time_ms=elapsed_ms,
                raw_response=data,
            )

            log.info(
                "Document classified",
                template_id=result.template_id,
                confidence=result.confidence,
                elapsed_ms=round(elapsed_ms, 1),
            )

            return result

        except (ClaudeAPIError, ClaudeRateLimitError):
            raise
        except Exception as e:
            raise ClassificationError(f"Classification failed: {e}") from e

    def extract_metadata(
        self,
        content: str,
        template: Template,
        base_specialist_prompt: str,
    ) -> ExtractionResult:
        """Extract metadata from a document using the specialist model.

        Args:
            content: Document OCR text content.
            template: Template defining extraction rules.
            base_specialist_prompt: Base system prompt for extraction.

        Returns:
            ExtractionResult with extracted fields.

        Raises:
            ExtractionError: If extraction fails.
        """
        log = logger.bind(operation="extract", template_id=template.id)

        # Build field list for prompt
        field_descriptions = "\n".join(
            f"- {f.name} ({f.type}): {f.description or 'No description'}"
            + (" [REQUIRED]" if f.required else "")
            for f in template.extraction.fields
        )

        system_prompt = f"""{base_specialist_prompt}

Template: {template.id} - {template.description}

Extraction Rules:
{template.extraction.rules}

Fields to extract:
{field_descriptions}
"""

        user_message = f"""Document content:
{content[:self.config.max_tokens * 10]}

Extract the requested fields and return JSON with:
- fields: Object mapping field names to extracted values
- confidence: Object mapping field names to confidence scores (0.0 to 1.0)
- notes: Any extraction notes or issues (optional)

Example format:
{{
  "fields": {{"issue_date": "2025-01-15", "total_gross": "123.45"}},
  "confidence": {{"issue_date": 0.95, "total_gross": 0.88}},
  "notes": "Amount was partially obscured"
}}
"""

        try:
            response_text, elapsed_ms = self._call_claude(
                model=self.config.specialist_model.value,
                system_prompt=system_prompt,
                user_message=user_message,
            )

            log.debug("Extraction response", response=response_text[:500])

            # Parse response
            try:
                data = _extract_json_from_response(response_text)
            except ValueError as e:
                raise ExtractionError(
                    f"Failed to parse extraction response: {e}",
                    template_id=template.id,
                    raw_response=response_text,
                ) from e

            # Build extracted fields
            fields: dict[str, ExtractedField] = {}
            raw_fields = data.get("fields", {})
            confidences = data.get("confidence", {})

            for field_def in template.extraction.fields:
                field_name = field_def.name
                raw_value = raw_fields.get(field_name)

                if raw_value is not None:
                    raw_value = str(raw_value) if raw_value else None

                confidence = float(confidences.get(field_name, 0.5))

                # Determine field type
                field_type = FieldType.STRING
                if field_def.type == "date":
                    field_type = FieldType.DATE
                elif field_def.type == "amount":
                    field_type = FieldType.AMOUNT
                elif field_def.type == "number":
                    field_type = FieldType.NUMBER
                elif field_def.type == "integer":
                    field_type = FieldType.INTEGER

                fields[field_name] = ExtractedField(
                    name=field_name,
                    raw_value=raw_value,
                    normalized_value=None,  # Will be normalized later
                    confidence=confidence,
                    field_type=field_type,
                )

            result = ExtractionResult(
                template_id=template.id,
                template_confidence=0.9,  # Already classified
                fields=fields,
                raw_response=data,
                processing_time_ms=elapsed_ms,
                extraction_notes=data.get("notes"),
            )

            log.info(
                "Metadata extracted",
                template_id=template.id,
                fields_extracted=result.extracted_count,
                overall_confidence=round(result.overall_confidence, 2),
                elapsed_ms=round(elapsed_ms, 1),
            )

            return result

        except (ClaudeAPIError, ClaudeRateLimitError):
            raise
        except ExtractionError:
            raise
        except Exception as e:
            raise ExtractionError(
                f"Extraction failed: {e}",
                template_id=template.id,
            ) from e

    def classify_and_extract(
        self,
        content: str,
        templates_config: TemplatesConfig,
    ) -> tuple[ClassificationResult, ExtractionResult]:
        """Classify a document and extract metadata in one call.

        Convenience method that chains classification and extraction.

        Args:
            content: Document OCR text content.
            templates_config: Templates configuration.

        Returns:
            Tuple of (ClassificationResult, ExtractionResult).

        Raises:
            ClassificationError: If classification fails.
            ExtractionError: If extraction fails.
        """
        # Step 1: Classify
        classification = self.classify_document(content, templates_config)

        # Step 2: Get template
        template = templates_config.get_template_by_id(classification.template_id)
        if not template:
            # Use fallback
            template = templates_config.get_template_by_id("fallback_general")
            if not template:
                raise ExtractionError(
                    f"Template not found and no fallback: {classification.template_id}",
                    template_id=classification.template_id,
                )

        # Step 3: Extract
        extraction = self.extract_metadata(
            content=content,
            template=template,
            base_specialist_prompt=templates_config.base_prompts.specialist,
        )

        # Update extraction with classification confidence
        extraction.template_confidence = classification.confidence

        return classification, extraction
