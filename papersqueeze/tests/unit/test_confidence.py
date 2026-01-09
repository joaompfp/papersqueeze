"""Tests for confidence scoring."""

import pytest

from papersqueeze.config.schema import Template, TemplateExtraction, TemplateField
from papersqueeze.models.extraction import ExtractedField, ExtractionResult, FieldType
from papersqueeze.services.confidence import ConfidenceFactor, ConfidenceScorer


@pytest.fixture
def scorer() -> ConfidenceScorer:
    return ConfidenceScorer()


@pytest.fixture
def template_with_required_fields() -> Template:
    return Template(
        id="test",
        description="Test",
        extraction=TemplateExtraction(
            rules="Test",
            fields=[
                TemplateField(name="issue_date", type="date", required=True),
                TemplateField(name="total_gross", type="amount", required=True),
                TemplateField(name="invoice_number", type="string", required=False),
            ],
        ),
        field_mapping={},
        title_format="Test",
    )


class TestConfidenceScorer:
    """Tests for confidence scoring."""

    def test_perfect_extraction_high_score(
        self,
        scorer: ConfidenceScorer,
        template_with_required_fields: Template,
    ) -> None:
        """All fields extracted with high confidence should score high."""
        extraction = ExtractionResult(
            template_id="test",
            template_confidence=0.95,
            fields={
                "issue_date": ExtractedField(
                    name="issue_date",
                    raw_value="2025-01-15",
                    normalized_value="2025-01-15",
                    confidence=0.95,
                    field_type=FieldType.DATE,
                ),
                "total_gross": ExtractedField(
                    name="total_gross",
                    raw_value="123.45",
                    normalized_value="123.45",
                    confidence=0.90,
                    field_type=FieldType.AMOUNT,
                ),
                "invoice_number": ExtractedField(
                    name="invoice_number",
                    raw_value="INV-001",
                    normalized_value="INV-001",
                    confidence=0.85,
                    field_type=FieldType.STRING,
                ),
            },
        )

        score = scorer.score_extraction(extraction, template_with_required_fields)

        assert score.overall >= 0.8
        assert score.factor_scores[ConfidenceFactor.REQUIRED_FIELDS_PRESENT] == 1.0
        assert score.factor_scores[ConfidenceFactor.FIELD_COMPLETENESS] == 1.0

    def test_missing_required_field_low_score(
        self,
        scorer: ConfidenceScorer,
        template_with_required_fields: Template,
    ) -> None:
        """Missing required fields should significantly lower score."""
        extraction = ExtractionResult(
            template_id="test",
            template_confidence=0.95,
            fields={
                "invoice_number": ExtractedField(
                    name="invoice_number",
                    raw_value="INV-001",
                    normalized_value="INV-001",
                    confidence=0.85,
                    field_type=FieldType.STRING,
                ),
            },
        )

        score = scorer.score_extraction(extraction, template_with_required_fields)

        # Missing both required fields
        assert score.factor_scores[ConfidenceFactor.REQUIRED_FIELDS_PRESENT] == 0.0
        assert score.overall < 0.7

    def test_low_confidence_extraction_lower_score(
        self,
        scorer: ConfidenceScorer,
        template_with_required_fields: Template,
    ) -> None:
        """Low confidence in required fields should lower score."""
        extraction = ExtractionResult(
            template_id="test",
            template_confidence=0.95,
            fields={
                "issue_date": ExtractedField(
                    name="issue_date",
                    raw_value="2025-01-15",
                    normalized_value="2025-01-15",
                    confidence=0.3,  # Low confidence
                    field_type=FieldType.DATE,
                ),
                "total_gross": ExtractedField(
                    name="total_gross",
                    raw_value="123.45",
                    normalized_value="123.45",
                    confidence=0.4,  # Low confidence
                    field_type=FieldType.AMOUNT,
                ),
            },
        )

        score = scorer.score_extraction(extraction, template_with_required_fields)

        # Required fields present but low confidence
        assert score.factor_scores[ConfidenceFactor.REQUIRED_FIELDS_PRESENT] == 0.0

    def test_format_validity_with_normalization_failures(
        self,
        scorer: ConfidenceScorer,
        template_with_required_fields: Template,
    ) -> None:
        """Fields that fail normalization should lower format validity score."""
        extraction = ExtractionResult(
            template_id="test",
            template_confidence=0.95,
            fields={
                "issue_date": ExtractedField(
                    name="issue_date",
                    raw_value="invalid date",
                    normalized_value=None,  # Failed normalization
                    confidence=0.5,
                    field_type=FieldType.DATE,
                ),
                "total_gross": ExtractedField(
                    name="total_gross",
                    raw_value="not a number",
                    normalized_value=None,  # Failed normalization
                    confidence=0.5,
                    field_type=FieldType.AMOUNT,
                ),
            },
        )

        score = scorer.score_extraction(extraction, template_with_required_fields)

        # Format validity should be low (raw values exist but no normalization)
        assert score.factor_scores[ConfidenceFactor.FORMAT_VALIDITY] == 0.5

    def test_is_confident_for_auto_apply(self, scorer: ConfidenceScorer) -> None:
        """Test auto-apply threshold checking."""
        from papersqueeze.services.confidence import ConfidenceScore

        high_score = ConfidenceScore(overall=0.8)
        low_score = ConfidenceScore(overall=0.5)

        assert scorer.is_confident_for_auto_apply(high_score, threshold=0.7) is True
        assert scorer.is_confident_for_auto_apply(low_score, threshold=0.7) is False

    def test_is_confident_for_suggestion(self, scorer: ConfidenceScorer) -> None:
        """Test suggestion threshold checking."""
        from papersqueeze.services.confidence import ConfidenceScore

        high_score = ConfidenceScore(overall=0.95)
        medium_score = ConfidenceScore(overall=0.85)

        assert scorer.is_confident_for_suggestion(high_score, threshold=0.9) is True
        assert scorer.is_confident_for_suggestion(medium_score, threshold=0.9) is False


class TestConfidenceScore:
    """Tests for ConfidenceScore dataclass."""

    def test_clamps_overall_score(self) -> None:
        from papersqueeze.services.confidence import ConfidenceScore

        score = ConfidenceScore(overall=1.5)
        assert score.overall == 1.0

        score = ConfidenceScore(overall=-0.5)
        assert score.overall == 0.0
