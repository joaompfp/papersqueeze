"""Title and display formatting utilities."""

import re
from string import Formatter
from typing import Any

# Unicode spaces for alignment in monospace fonts
FIGURE_SPACE = "\u2007"  # Same width as digits
NON_BREAKING_SPACE = "\u00A0"

# Default column widths for ledger-style titles
DEFAULT_COL_WIDTHS = {
    "date": 10,        # YYYY-MM-DD
    "reference": 32,   # Contract refs, invoice numbers
    "metric": 12,      # Consumption values with units
    "amount": 12,      # Monetary amounts with currency
}


class SafeDict(dict):
    """Dictionary that returns placeholder for missing keys in format strings."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def format_ledger_title(
    format_string: str,
    values: dict[str, Any],
    col_widths: dict[str, int] | None = None,
) -> str:
    """Format a document title in ledger style with aligned columns.

    Uses the format string from template configuration with extracted values.

    Args:
        format_string: Format string with {field} placeholders.
        values: Dictionary of field values to substitute.
        col_widths: Optional custom column widths.

    Returns:
        Formatted title string.

    Examples:
        >>> format_ledger_title(
        ...     "{issue_date} | {ref} | {amount} EUR",
        ...     {"issue_date": "2025-01-15", "ref": "INV-001", "amount": "123.45"}
        ... )
        '2025-01-15 | INV-001 | 123.45 EUR'
    """
    widths = {**DEFAULT_COL_WIDTHS, **(col_widths or {})}

    # Use SafeDict to handle missing keys gracefully
    safe_values = SafeDict(values)

    # Format with safe substitution
    try:
        result = format_string.format_map(safe_values)
    except (KeyError, ValueError):
        # Fallback: just substitute what we can
        result = format_string
        for key, value in values.items():
            result = result.replace(f"{{{key}}}", str(value) if value else "")

    # Clean up multiple spaces and trim
    result = " ".join(result.split())

    # Replace empty placeholders with dashes
    result = re.sub(r"\{\w+\}", "-", result)

    return result


def format_amount_display(
    amount: str | float | None,
    currency: str = "EUR",
    use_figure_space: bool = True,
) -> str:
    """Format an amount for display with proper alignment.

    Args:
        amount: Amount value.
        currency: Currency code or symbol.
        use_figure_space: Use figure space for digit alignment.

    Returns:
        Formatted amount string.

    Examples:
        >>> format_amount_display("1234.56", "EUR")
        '1234.56 EUR'
        >>> format_amount_display(None)
        '-'
    """
    if amount is None:
        return "-"

    if isinstance(amount, float):
        amount = f"{amount:.2f}"

    amount_str = str(amount).strip()
    if not amount_str:
        return "-"

    return f"{amount_str} {currency}"


def format_metric_display(
    value: str | float | None,
    unit: str,
) -> str:
    """Format a metric value for display.

    Args:
        value: Metric value.
        unit: Unit string (kWh, m3, etc.).

    Returns:
        Formatted metric string.

    Examples:
        >>> format_metric_display("123.45", "kWh")
        '123.45 kWh'
        >>> format_metric_display(None, "m3")
        '-'
    """
    if value is None:
        return "-"

    value_str = str(value).strip()
    if not value_str:
        return "-"

    return f"{value_str} {unit}"


def truncate_text(
    text: str,
    max_length: int,
    ellipsis: str = "...",
) -> str:
    """Truncate text to maximum length with ellipsis.

    Args:
        text: Text to truncate.
        max_length: Maximum length including ellipsis.
        ellipsis: Ellipsis string to append.

    Returns:
        Truncated text.
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(ellipsis)] + ellipsis


def pad_right(
    text: str,
    width: int,
    fill_char: str = " ",
) -> str:
    """Pad text on the right to specified width.

    Args:
        text: Text to pad.
        width: Desired width.
        fill_char: Character to use for padding.

    Returns:
        Padded text.
    """
    if len(text) >= width:
        return text[:width]
    return text + fill_char * (width - len(text))


def pad_left(
    text: str,
    width: int,
    fill_char: str = " ",
) -> str:
    """Pad text on the left to specified width.

    Args:
        text: Text to pad.
        width: Desired width.
        fill_char: Character to use for padding.

    Returns:
        Padded text.
    """
    if len(text) >= width:
        return text[:width]
    return fill_char * (width - len(text)) + text


def build_title_from_extraction(
    template_title_format: str,
    extraction_fields: dict[str, Any],
    document_date: str | None = None,
) -> str:
    """Build a document title from template format and extracted fields.

    Args:
        template_title_format: Format string from template.
        extraction_fields: Dictionary of extracted field values.
        document_date: Optional fallback date if not in extraction.

    Returns:
        Formatted title string.
    """
    # Build values dict from extraction
    values = {}
    for key, value in extraction_fields.items():
        if value is not None:
            values[key] = str(value)

    # Add document date as fallback for issue_date
    if "issue_date" not in values and document_date:
        values["issue_date"] = document_date

    return format_ledger_title(template_title_format, values)


def sanitize_filename(text: str, max_length: int = 200) -> str:
    """Sanitize text for use in filenames.

    Args:
        text: Text to sanitize.
        max_length: Maximum filename length.

    Returns:
        Sanitized filename-safe string.
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    result = text
    for char in invalid_chars:
        result = result.replace(char, "-")

    # Replace multiple dashes with single dash
    result = re.sub(r"-+", "-", result)

    # Remove leading/trailing dashes and spaces
    result = result.strip("- ")

    # Truncate
    if len(result) > max_length:
        result = result[:max_length].rstrip("- ")

    return result
