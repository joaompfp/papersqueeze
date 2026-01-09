"""Smart merge strategy for combining AI extractions with existing metadata."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from papersqueeze.models.document import Document
from papersqueeze.models.extraction import ExtractionResult, ProposedChange
from papersqueeze.services.confidence import ConfidenceScore
from papersqueeze.utils.normalization import is_empty_value, values_match

logger = structlog.get_logger()


class MergeDecision(str, Enum):
    """Decision for how to merge a field."""

    KEEP_EXISTING = "keep"           # Keep paperless-ngx value (authoritative)
    USE_AI = "use_ai"                # Use AI value (fills empty field)
    NEEDS_REVIEW = "needs_review"    # AI suggests change, needs human review
    SKIP = "skip"                    # Skip this field (no value from either)


@dataclass
class FieldMergeResult:
    """Result of merging a single field."""

    field_name: str
    existing_value: Any
    ai_value: Any
    ai_confidence: float
    decision: MergeDecision
    final_value: Any
    reason: str

    @property
    def is_change(self) -> bool:
        """Check if this results in a change."""
        return self.decision in (MergeDecision.USE_AI, MergeDecision.NEEDS_REVIEW)

    @property
    def is_auto_apply(self) -> bool:
        """Check if this can be auto-applied."""
        return self.decision == MergeDecision.USE_AI


@dataclass
class MergeResult:
    """Result of merging all fields."""

    field_results: list[FieldMergeResult]
    auto_apply_changes: list[ProposedChange]
    review_changes: list[ProposedChange]
    kept_existing: list[str]

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.auto_apply_changes or self.review_changes)

    @property
    def needs_review(self) -> bool:
        """Check if any changes need review."""
        return bool(self.review_changes)


class MergeStrategy:
    """Smart merge strategy: Paperless-ngx is the source of truth.

    Philosophy:
    1. If existing value is empty -> Use AI value (if confident enough)
    2. If existing value exists:
       - If AI agrees with existing -> Keep existing (KEEP_EXISTING)
       - If AI disagrees with high confidence -> Queue for review (NEEDS_REVIEW)
       - If AI disagrees with low confidence -> Keep existing (KEEP_EXISTING)
    """

    def __init__(
        self,
        auto_apply_threshold: float = 0.7,
        suggestion_threshold: float = 0.9,
    ) -> None:
        """Initialize merge strategy.

        Args:
            auto_apply_threshold: Minimum confidence to auto-fill empty fields.
            suggestion_threshold: Minimum confidence to suggest overwriting.
        """
        self.auto_apply_threshold = auto_apply_threshold
        self.suggestion_threshold = suggestion_threshold

    def merge_field(
        self,
        field_name: str,
        existing_value: Any,
        ai_value: Any,
        ai_confidence: float,
    ) -> FieldMergeResult:
        """Determine how to merge a single field.

        Args:
            field_name: Name of the field.
            existing_value: Current value in paperless-ngx.
            ai_value: Value extracted by AI.
            ai_confidence: AI's confidence in the extraction.

        Returns:
            FieldMergeResult with decision and final value.
        """
        log = logger.bind(field=field_name)

        existing_empty = is_empty_value(existing_value)
        ai_empty = is_empty_value(ai_value)

        # Case 1: Neither has a value
        if existing_empty and ai_empty:
            return FieldMergeResult(
                field_name=field_name,
                existing_value=existing_value,
                ai_value=ai_value,
                ai_confidence=ai_confidence,
                decision=MergeDecision.SKIP,
                final_value=None,
                reason="No value from either source",
            )

        # Case 2: Only existing has value (AI didn't extract)
        if not existing_empty and ai_empty:
            return FieldMergeResult(
                field_name=field_name,
                existing_value=existing_value,
                ai_value=ai_value,
                ai_confidence=ai_confidence,
                decision=MergeDecision.KEEP_EXISTING,
                final_value=existing_value,
                reason="AI did not extract this field",
            )

        # Case 3: Only AI has value (existing is empty) - FILL
        if existing_empty and not ai_empty:
            if ai_confidence >= self.auto_apply_threshold:
                log.debug(
                    "Auto-filling empty field",
                    value=ai_value,
                    confidence=ai_confidence,
                )
                return FieldMergeResult(
                    field_name=field_name,
                    existing_value=existing_value,
                    ai_value=ai_value,
                    ai_confidence=ai_confidence,
                    decision=MergeDecision.USE_AI,
                    final_value=ai_value,
                    reason=f"Filling empty field (confidence: {ai_confidence:.0%})",
                )
            else:
                log.debug(
                    "Low confidence, queuing for review",
                    value=ai_value,
                    confidence=ai_confidence,
                )
                return FieldMergeResult(
                    field_name=field_name,
                    existing_value=existing_value,
                    ai_value=ai_value,
                    ai_confidence=ai_confidence,
                    decision=MergeDecision.NEEDS_REVIEW,
                    final_value=existing_value,
                    reason=f"Low confidence ({ai_confidence:.0%}), needs review",
                )

        # Case 4: Both have values - compare
        if values_match(existing_value, ai_value):
            return FieldMergeResult(
                field_name=field_name,
                existing_value=existing_value,
                ai_value=ai_value,
                ai_confidence=ai_confidence,
                decision=MergeDecision.KEEP_EXISTING,
                final_value=existing_value,
                reason="AI agrees with existing value",
            )

        # Values differ - AI wants to change
        if ai_confidence >= self.suggestion_threshold:
            log.debug(
                "High confidence change, queuing for review",
                existing=existing_value,
                proposed=ai_value,
                confidence=ai_confidence,
            )
            return FieldMergeResult(
                field_name=field_name,
                existing_value=existing_value,
                ai_value=ai_value,
                ai_confidence=ai_confidence,
                decision=MergeDecision.NEEDS_REVIEW,
                final_value=existing_value,  # Don't change yet
                reason=f"AI suggests different value (confidence: {ai_confidence:.0%})",
            )
        else:
            log.debug(
                "Low confidence disagreement, keeping existing",
                existing=existing_value,
                proposed=ai_value,
                confidence=ai_confidence,
            )
            return FieldMergeResult(
                field_name=field_name,
                existing_value=existing_value,
                ai_value=ai_value,
                ai_confidence=ai_confidence,
                decision=MergeDecision.KEEP_EXISTING,
                final_value=existing_value,
                reason=f"AI confidence too low to suggest change ({ai_confidence:.0%})",
            )

    def merge_document(
        self,
        document: Document,
        extraction: ExtractionResult,
        field_mapping: dict[str, str],
        confidence: ConfidenceScore,
    ) -> MergeResult:
        """Merge AI extraction with existing document metadata.

        Args:
            document: Document with existing metadata.
            extraction: AI extraction result.
            field_mapping: Map of extracted field names to paperless field names.
            confidence: Overall confidence score.

        Returns:
            MergeResult with all field decisions.
        """
        log = logger.bind(doc_id=document.id)
        log.info("Merging extraction with existing metadata")

        field_results: list[FieldMergeResult] = []
        auto_apply_changes: list[ProposedChange] = []
        review_changes: list[ProposedChange] = []
        kept_existing: list[str] = []

        for extracted_name, paperless_name in field_mapping.items():
            # Get AI value
            ai_field = extraction.fields.get(extracted_name)
            if not ai_field:
                continue

            ai_value = ai_field.normalized_value or ai_field.raw_value
            ai_confidence = ai_field.confidence

            # Get existing value from document
            existing_value = document.get_custom_field_value(paperless_name)

            # Merge
            result = self.merge_field(
                field_name=paperless_name,
                existing_value=existing_value,
                ai_value=ai_value,
                ai_confidence=ai_confidence,
            )
            field_results.append(result)

            # Categorize result
            if result.decision == MergeDecision.USE_AI:
                auto_apply_changes.append(
                    ProposedChange(
                        field_name=paperless_name,
                        current_value=existing_value,
                        proposed_value=ai_value,
                        confidence=ai_confidence,
                        source="ai",
                        reason=result.reason,
                    )
                )
            elif result.decision == MergeDecision.NEEDS_REVIEW:
                review_changes.append(
                    ProposedChange(
                        field_name=paperless_name,
                        current_value=existing_value,
                        proposed_value=ai_value,
                        confidence=ai_confidence,
                        source="ai",
                        reason=result.reason,
                    )
                )
            elif result.decision == MergeDecision.KEEP_EXISTING:
                kept_existing.append(paperless_name)

        log.info(
            "Merge complete",
            auto_apply=len(auto_apply_changes),
            needs_review=len(review_changes),
            kept_existing=len(kept_existing),
        )

        return MergeResult(
            field_results=field_results,
            auto_apply_changes=auto_apply_changes,
            review_changes=review_changes,
            kept_existing=kept_existing,
        )

    def merge_title(
        self,
        existing_title: str,
        proposed_title: str,
        confidence: float,
    ) -> FieldMergeResult:
        """Merge document title.

        Titles are treated specially - we suggest changes more readily
        since the AI-generated title follows a consistent format.

        Args:
            existing_title: Current document title.
            proposed_title: AI-proposed title.
            confidence: Confidence in the proposed title.

        Returns:
            FieldMergeResult for the title.
        """
        # Check if existing title looks like a default/auto-generated one
        is_default_title = (
            existing_title.lower().startswith("document")
            or existing_title.lower().startswith("scan")
            or len(existing_title) < 10
        )

        if is_default_title and confidence >= self.auto_apply_threshold:
            return FieldMergeResult(
                field_name="title",
                existing_value=existing_title,
                ai_value=proposed_title,
                ai_confidence=confidence,
                decision=MergeDecision.USE_AI,
                final_value=proposed_title,
                reason="Replacing default/auto-generated title",
            )

        if values_match(existing_title, proposed_title):
            return FieldMergeResult(
                field_name="title",
                existing_value=existing_title,
                ai_value=proposed_title,
                ai_confidence=confidence,
                decision=MergeDecision.KEEP_EXISTING,
                final_value=existing_title,
                reason="AI agrees with existing title",
            )

        # Always queue title changes for review unless it's a default title
        return FieldMergeResult(
            field_name="title",
            existing_value=existing_title,
            ai_value=proposed_title,
            ai_confidence=confidence,
            decision=MergeDecision.NEEDS_REVIEW,
            final_value=existing_title,
            reason="Title change requires review",
        )
