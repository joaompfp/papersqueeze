"""Tests for normalization utilities."""

import pytest
from datetime import date

from papersqueeze.utils.normalization import (
    normalize_date,
    normalize_amount,
    normalize_number,
    normalize_text,
    normalize_nif,
    normalize_mb_reference,
    calculate_due_date,
    is_empty_value,
    values_match,
)


class TestNormalizeDate:
    """Tests for date normalization."""

    def test_iso_format(self) -> None:
        assert normalize_date("2025-01-15") == "2025-01-15"

    def test_european_dash_format(self) -> None:
        assert normalize_date("15-01-2025") == "2025-01-15"

    def test_european_slash_format(self) -> None:
        assert normalize_date("15/01/2025") == "2025-01-15"

    def test_european_dot_format(self) -> None:
        assert normalize_date("15.01.2025") == "2025-01-15"

    def test_date_object(self) -> None:
        assert normalize_date(date(2025, 1, 15)) == "2025-01-15"

    def test_none_returns_none(self) -> None:
        assert normalize_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert normalize_date("") is None
        assert normalize_date("   ") is None

    def test_invalid_format_returns_none(self) -> None:
        assert normalize_date("not a date") is None
        assert normalize_date("2025/13/45") is None

    def test_custom_output_format(self) -> None:
        assert normalize_date("2025-01-15", "%d/%m/%Y") == "15/01/2025"


class TestNormalizeAmount:
    """Tests for amount normalization."""

    def test_european_format(self) -> None:
        """European: comma is decimal, dot is thousands."""
        assert normalize_amount("1.234,56") == "1234.56"

    def test_european_with_currency(self) -> None:
        assert normalize_amount("1.234,56 €") == "1234.56"
        assert normalize_amount("€ 1.234,56") == "1234.56"
        assert normalize_amount("1.234,56 EUR") == "1234.56"

    def test_us_format(self) -> None:
        """US: period is decimal, comma is thousands."""
        assert normalize_amount("1,234.56") == "1234.56"

    def test_simple_european(self) -> None:
        assert normalize_amount("123,45") == "123.45"

    def test_simple_us(self) -> None:
        assert normalize_amount("123.45") == "123.45"

    def test_integer(self) -> None:
        assert normalize_amount("1234") == "1234.00"

    def test_numeric_input(self) -> None:
        assert normalize_amount(123.45) == "123.45"
        assert normalize_amount(1234) == "1234.00"

    def test_negative_amount(self) -> None:
        assert normalize_amount("-123,45") == "-123.45"

    def test_none_returns_none(self) -> None:
        assert normalize_amount(None) is None

    def test_empty_returns_none(self) -> None:
        assert normalize_amount("") is None
        assert normalize_amount("   ") is None

    def test_invalid_returns_none(self) -> None:
        assert normalize_amount("not a number") is None

    def test_custom_decimal_places(self) -> None:
        assert normalize_amount("123.456789", decimal_places=4) == "123.4568"


class TestNormalizeNumber:
    """Tests for number normalization."""

    def test_with_unit_suffix(self) -> None:
        assert normalize_number("123 kWh") == "123"
        assert normalize_number("8 m3") == "8"
        assert normalize_number("6.9 kVA") == "6.9"

    def test_decimal_with_unit(self) -> None:
        assert normalize_number("123,45 kWh") == "123.45"

    def test_integer(self) -> None:
        assert normalize_number("123") == "123"
        assert normalize_number(123) == "123"

    def test_float(self) -> None:
        assert normalize_number(123.45) == "123.45"
        assert normalize_number(123.0) == "123"


class TestNormalizeText:
    """Tests for text normalization."""

    def test_strips_whitespace(self) -> None:
        assert normalize_text("  hello world  ") == "hello world"

    def test_collapses_multiple_spaces(self) -> None:
        assert normalize_text("hello    world") == "hello world"

    def test_handles_newlines(self) -> None:
        assert normalize_text("hello\n\nworld") == "hello world"

    def test_truncation(self) -> None:
        result = normalize_text("hello world", max_length=8)
        assert result == "hello..."
        assert len(result) <= 8

    def test_none_returns_none(self) -> None:
        assert normalize_text(None) is None

    def test_empty_returns_none(self) -> None:
        assert normalize_text("") is None
        assert normalize_text("   ") is None


class TestNormalizeNif:
    """Tests for Portuguese NIF normalization."""

    def test_valid_nif(self) -> None:
        assert normalize_nif("123456789") == "123456789"

    def test_nif_with_spaces(self) -> None:
        assert normalize_nif("123 456 789") == "123456789"

    def test_nif_with_pt_prefix(self) -> None:
        assert normalize_nif("PT123456789") == "123456789"

    def test_invalid_length(self) -> None:
        assert normalize_nif("12345") is None
        assert normalize_nif("1234567890") is None

    def test_none_returns_none(self) -> None:
        assert normalize_nif(None) is None


class TestNormalizeMbReference:
    """Tests for Multibanco reference normalization."""

    def test_9_digit_reference(self) -> None:
        assert normalize_mb_reference("123456789") == "123456789"

    def test_15_digit_reference(self) -> None:
        assert normalize_mb_reference("123456789012345") == "123456789012345"

    def test_reference_with_spaces(self) -> None:
        assert normalize_mb_reference("123 456 789") == "123456789"

    def test_invalid_length(self) -> None:
        assert normalize_mb_reference("12345") is None

    def test_none_returns_none(self) -> None:
        assert normalize_mb_reference(None) is None


class TestCalculateDueDate:
    """Tests for due date calculation."""

    def test_from_string(self) -> None:
        assert calculate_due_date("2025-01-15", 15) == "2025-01-30"

    def test_from_date(self) -> None:
        assert calculate_due_date(date(2025, 1, 15), 15) == "2025-01-30"

    def test_month_overflow(self) -> None:
        assert calculate_due_date("2025-01-20", 15) == "2025-02-04"

    def test_invalid_date(self) -> None:
        assert calculate_due_date("invalid", 15) is None


class TestIsEmptyValue:
    """Tests for empty value checking."""

    def test_none_is_empty(self) -> None:
        assert is_empty_value(None) is True

    def test_empty_string_is_empty(self) -> None:
        assert is_empty_value("") is True
        assert is_empty_value("   ") is True

    def test_value_not_empty(self) -> None:
        assert is_empty_value("hello") is False
        assert is_empty_value(0) is False
        assert is_empty_value(123) is False


class TestValuesMatch:
    """Tests for value matching."""

    def test_both_empty(self) -> None:
        assert values_match(None, None) is True
        assert values_match("", "") is True
        assert values_match(None, "") is True

    def test_one_empty(self) -> None:
        assert values_match("hello", None) is False
        assert values_match(None, "hello") is False

    def test_same_string(self) -> None:
        assert values_match("hello", "hello") is True
        assert values_match("HELLO", "hello") is True  # Case insensitive

    def test_same_amount_different_format(self) -> None:
        assert values_match("123,45", "123.45") is True
        assert values_match("1.234,56", "1234.56") is True

    def test_same_date_different_format(self) -> None:
        assert values_match("15/01/2025", "2025-01-15") is True

    def test_different_values(self) -> None:
        assert values_match("123.45", "123.46") is False
        assert values_match("hello", "world") is False
