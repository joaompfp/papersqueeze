"""Confidence scoring for AI extractions."""

from dataclasses import dataclass, field
from enum import Enum

from papersqueeze.config.schema import Template
from papersqueeze.models.extraction import ExtractionResult


class ConfidenceFactor(str, Enum):
    """Factors that contribute to confidence scoring."""

    FIELD_COMPLETENESS = "completeness"
    FORMAT_VALIDITY = "format_valid"
    CROSS_FIELD_CONSISTENCY = "consistency"
    TEMPLATE_MATCH_QUALITY = "template_match"
    REQUIRED_FIELDS_PRESENT = "required_fields"


@dataclass
class ConfidenceScore:
    """Detailed confidence score for an extraction."""

    overall: float
    field_scores: dict[str, float] = field(default_factory=dict)
    factor_scores: dict[ConfidenceFactor, float] = field(default_factory=dict)
    explanation: str = ""

    def __post_init__(self) -> None:
        """Clamp overall score to valid range."""
        self.overall = max(0.0, min(1.0, self.overall))


class ConfidenceScorer:
    """Calculate confidence scores for AI extractions.

    Scoring is based on multiple factors:
    - Field completeness (% of expected fields extracted)
    - Format validity (dates, amounts parse correctly)
    - Cross-field consistency (e.g., gross = net + VAT)
    - Template match quality (classification confidence)
    - Required fields presence
    """

    # Weights for each factor (should sum to 1.0)
    FACTOR_WEIGHTS = {
        ConfidenceFactor.TEMPLATE_MATCH_QUALITY: 0.20,
        ConfidenceFactor.REQUIRED_FIELDS_PRESENT: 0.30,
        ConfidenceFactor.FIELD_COMPLETENESS: 0.20,
        ConfidenceFactor.FORMAT_VALIDITY: 0.20,
        ConfidenceFactor.CROSS_FIELD_CONSISTENCY: 0.10,
    }

    def score_extraction(
        self,
        extraction: ExtractionResult,
        template: Template,
    ) -> ConfidenceScore:
        """Calculate comprehensive confidence score for extraction.

        Args:
            extraction: Extraction result to score.
            template: Template that was used for extraction.

        Returns:
            Detailed ConfidenceScore.
        """
        factor_scores: dict[ConfidenceFactor, float] = {}

        # Factor 1: Template match quality
        factor_scores[ConfidenceFactor.TEMPLATE_MATCH_QUALITY] = (
            extraction.template_confidence
        )

        # Factor 2: Required fields present
        factor_scores[ConfidenceFactor.REQUIRED_FIELDS_PRESENT] = (
            self._score_required_fields(extraction, template)
        )

        # Factor 3: Field completeness
        factor_scores[ConfidenceFactor.FIELD_COMPLETENESS] = (
            self._score_completeness(extraction, template)
        )

        # Factor 4: Format validity
        factor_scores[ConfidenceFactor.FORMAT_VALIDITY] = (
            self._score_format_validity(extraction)
        )

        # Factor 5: Cross-field consistency
        factor_scores[ConfidenceFactor.CROSS_FIELD_CONSISTENCY] = (
            self._score_consistency(extraction)
        )

        # Calculate weighted overall score
        overall = sum(
            factor_scores[factor] * weight
            for factor, weight in self.FACTOR_WEIGHTS.items()
        )

        # Build explanation
        explanations = []
        for factor, score in factor_scores.items():
            if score < 0.7:
                explanations.append(f"{factor.value}: {score:.0%}")

        explanation = (
            f"Low scores: {', '.join(explanations)}" if explanations else "All factors good"
        )

        # Collect individual field confidence scores
        field_scores = {
            name: field.confidence
            for name, field in extraction.fields.items()
            if field.has_value
        }

        return ConfidenceScore(
            overall=overall,
            field_scores=field_scores,
            factor_scores=factor_scores,
            explanation=explanation,
        )

    def _score_required_fields(
        self,
        extraction: ExtractionResult,
        template: Template,
    ) -> float:
        """Score based on presence of required fields."""
        required_fields = [f for f in template.extraction.fields if f.required]

        if not required_fields:
            return 1.0  # No required fields = perfect score

        present_count = 0
        for field_def in required_fields:
            field = extraction.fields.get(field_def.name)
            if field and field.has_value and field.confidence >= 0.5:
                present_count += 1

        return present_count / len(required_fields)

    def _score_completeness(
        self,
        extraction: ExtractionResult,
        template: Template,
    ) -> float:
        """Score based on percentage of fields extracted."""
        expected_fields = [f.name for f in template.extraction.fields]

        if not expected_fields:
            return 1.0

        extracted_count = sum(
            1 for name in expected_fields
            if name in extraction.fields and extraction.fields[name].has_value
        )

        return extracted_count / len(expected_fields)

    def _score_format_validity(self, extraction: ExtractionResult) -> float:
        """Score based on whether extracted values have valid formats."""
        if not extraction.fields:
            return 1.0

        valid_count = 0
        total_count = 0

        for field in extraction.fields.values():
            if not field.has_value:
                continue

            total_count += 1

            # Check if normalization succeeded
            if field.normalized_value is not None:
                valid_count += 1
            elif field.raw_value is not None:
                # Raw value exists but couldn't normalize - still partially valid
                valid_count += 0.5

        if total_count == 0:
            return 1.0

        return valid_count / total_count

    def _score_consistency(self, extraction: ExtractionResult) -> float:
        """Score based on cross-field consistency checks.

        Examples:
        - total_gross should >= total_net
        - due_date should be after issue_date
        """
        checks_passed = 0
        checks_total = 0

        # Check: gross >= net (if both present)
        gross = extraction.get_field("total_gross")
        net = extraction.get_field("total_net")
        if gross and net and gross.has_value and net.has_value:
            checks_total += 1
            try:
                gross_val = float(gross.normalized_value or gross.raw_value or 0)
                net_val = float(net.normalized_value or net.raw_value or 0)
                if gross_val >= net_val:
                    checks_passed += 1
            except (ValueError, TypeError):
                pass

        # Check: due_date > issue_date (if both present)
        issue = extraction.get_field("issue_date")
        due = extraction.get_field("due_date")
        if issue and due and issue.has_value and due.has_value:
            checks_total += 1
            issue_val = issue.normalized_value or issue.raw_value
            due_val = due.normalized_value or due.raw_value
            if issue_val and due_val and due_val >= issue_val:
                checks_passed += 1

        # If no consistency checks applicable, return perfect score
        if checks_total == 0:
            return 1.0

        return checks_passed / checks_total

    def is_confident_for_auto_apply(
        self,
        score: ConfidenceScore,
        threshold: float = 0.7,
    ) -> bool:
        """Check if extraction is confident enough to auto-apply.

        Args:
            score: Confidence score to check.
            threshold: Minimum confidence threshold.

        Returns:
            True if confident enough for auto-apply.
        """
        return score.overall >= threshold

    def is_confident_for_suggestion(
        self,
        score: ConfidenceScore,
        threshold: float = 0.9,
    ) -> bool:
        """Check if extraction is confident enough to suggest changes.

        Higher threshold than auto-apply because we're proposing to
        change existing values.

        Args:
            score: Confidence score to check.
            threshold: Minimum confidence threshold.

        Returns:
            True if confident enough to suggest.
        """
        return score.overall >= threshold
