"""Tests for merge strategy."""

import pytest

from papersqueeze.services.merge import MergeDecision, MergeStrategy


class TestMergeField:
    """Tests for single field merging."""

    @pytest.fixture
    def strategy(self) -> MergeStrategy:
        return MergeStrategy(
            auto_apply_threshold=0.7,
            suggestion_threshold=0.9,
        )

    def test_both_empty_skips(self, strategy: MergeStrategy) -> None:
        """When neither has a value, skip."""
        result = strategy.merge_field(
            field_name="test",
            existing_value=None,
            ai_value=None,
            ai_confidence=0.0,
        )
        assert result.decision == MergeDecision.SKIP
        assert result.final_value is None

    def test_only_existing_keeps_existing(self, strategy: MergeStrategy) -> None:
        """When AI didn't extract, keep existing."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="existing",
            ai_value=None,
            ai_confidence=0.0,
        )
        assert result.decision == MergeDecision.KEEP_EXISTING
        assert result.final_value == "existing"

    def test_only_ai_high_confidence_uses_ai(self, strategy: MergeStrategy) -> None:
        """When existing is empty and AI is confident, fill with AI."""
        result = strategy.merge_field(
            field_name="test",
            existing_value=None,
            ai_value="ai_value",
            ai_confidence=0.85,
        )
        assert result.decision == MergeDecision.USE_AI
        assert result.final_value == "ai_value"

    def test_only_ai_low_confidence_needs_review(self, strategy: MergeStrategy) -> None:
        """When existing is empty but AI has low confidence, needs review."""
        result = strategy.merge_field(
            field_name="test",
            existing_value=None,
            ai_value="ai_value",
            ai_confidence=0.5,
        )
        assert result.decision == MergeDecision.NEEDS_REVIEW
        assert result.final_value is None  # Don't apply yet

    def test_both_match_keeps_existing(self, strategy: MergeStrategy) -> None:
        """When AI agrees with existing, keep existing."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="123.45",
            ai_value="123.45",
            ai_confidence=0.95,
        )
        assert result.decision == MergeDecision.KEEP_EXISTING
        assert result.final_value == "123.45"

    def test_both_match_normalized_keeps_existing(self, strategy: MergeStrategy) -> None:
        """When AI agrees (after normalization), keep existing."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="123.45",
            ai_value="123,45",  # European format
            ai_confidence=0.95,
        )
        assert result.decision == MergeDecision.KEEP_EXISTING

    def test_different_high_confidence_needs_review(self, strategy: MergeStrategy) -> None:
        """When AI disagrees with high confidence, queue for review."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="100.00",
            ai_value="200.00",
            ai_confidence=0.95,
        )
        assert result.decision == MergeDecision.NEEDS_REVIEW
        assert result.final_value == "100.00"  # Keep existing for now

    def test_different_low_confidence_keeps_existing(self, strategy: MergeStrategy) -> None:
        """When AI disagrees with low confidence, keep existing."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="100.00",
            ai_value="200.00",
            ai_confidence=0.6,
        )
        assert result.decision == MergeDecision.KEEP_EXISTING
        assert result.final_value == "100.00"

    def test_empty_string_treated_as_empty(self, strategy: MergeStrategy) -> None:
        """Empty string should be treated as empty value."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="",
            ai_value="ai_value",
            ai_confidence=0.85,
        )
        assert result.decision == MergeDecision.USE_AI

    def test_whitespace_only_treated_as_empty(self, strategy: MergeStrategy) -> None:
        """Whitespace-only string should be treated as empty."""
        result = strategy.merge_field(
            field_name="test",
            existing_value="   ",
            ai_value="ai_value",
            ai_confidence=0.85,
        )
        assert result.decision == MergeDecision.USE_AI


class TestMergeTitle:
    """Tests for title merging."""

    @pytest.fixture
    def strategy(self) -> MergeStrategy:
        return MergeStrategy()

    def test_default_title_replaced(self, strategy: MergeStrategy) -> None:
        """Default/auto-generated titles should be replaced."""
        result = strategy.merge_title(
            existing_title="Document_001.pdf",
            proposed_title="2025-01-15 | Invoice | 123.45 EUR",
            confidence=0.8,
        )
        assert result.decision == MergeDecision.USE_AI

    def test_scan_title_replaced(self, strategy: MergeStrategy) -> None:
        """Scan titles should be replaced."""
        result = strategy.merge_title(
            existing_title="Scan_2025-01-15",
            proposed_title="2025-01-15 | Invoice | 123.45 EUR",
            confidence=0.8,
        )
        assert result.decision == MergeDecision.USE_AI

    def test_short_title_replaced(self, strategy: MergeStrategy) -> None:
        """Very short titles should be replaced."""
        result = strategy.merge_title(
            existing_title="Invoice",
            proposed_title="2025-01-15 | Invoice | 123.45 EUR",
            confidence=0.8,
        )
        assert result.decision == MergeDecision.USE_AI

    def test_custom_title_needs_review(self, strategy: MergeStrategy) -> None:
        """Custom titles should need review before changing."""
        result = strategy.merge_title(
            existing_title="My custom invoice title from January",
            proposed_title="2025-01-15 | Invoice | 123.45 EUR",
            confidence=0.95,
        )
        assert result.decision == MergeDecision.NEEDS_REVIEW

    def test_matching_title_keeps_existing(self, strategy: MergeStrategy) -> None:
        """If AI proposes same title, keep existing."""
        title = "2025-01-15 | Invoice | 123.45 EUR"
        result = strategy.merge_title(
            existing_title=title,
            proposed_title=title,
            confidence=0.95,
        )
        assert result.decision == MergeDecision.KEEP_EXISTING


class TestFieldMergeResult:
    """Tests for FieldMergeResult properties."""

    def test_is_change(self) -> None:
        from papersqueeze.services.merge import FieldMergeResult

        result = FieldMergeResult(
            field_name="test",
            existing_value=None,
            ai_value="new",
            ai_confidence=0.9,
            decision=MergeDecision.USE_AI,
            final_value="new",
            reason="test",
        )
        assert result.is_change is True

        result.decision = MergeDecision.KEEP_EXISTING
        assert result.is_change is False

    def test_is_auto_apply(self) -> None:
        from papersqueeze.services.merge import FieldMergeResult

        result = FieldMergeResult(
            field_name="test",
            existing_value=None,
            ai_value="new",
            ai_confidence=0.9,
            decision=MergeDecision.USE_AI,
            final_value="new",
            reason="test",
        )
        assert result.is_auto_apply is True

        result.decision = MergeDecision.NEEDS_REVIEW
        assert result.is_auto_apply is False
