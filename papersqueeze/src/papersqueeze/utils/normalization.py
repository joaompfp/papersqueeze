"""Data normalization utilities for dates, amounts, and text."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

logger = structlog.get_logger()

# Date format patterns to try (order matters - more specific first)
DATE_FORMATS = [
    "%Y-%m-%d",      # ISO format: 2025-01-15
    "%d-%m-%Y",      # European: 15-01-2025
    "%d/%m/%Y",      # European with slash: 15/01/2025
    "%d.%m.%Y",      # European with dot: 15.01.2025
    "%Y/%m/%d",      # ISO with slash: 2025/01/15
    "%Y.%m.%d",      # ISO with dot: 2025.01.15
    "%d %b %Y",      # 15 Jan 2025
    "%d %B %Y",      # 15 January 2025
    "%B %d, %Y",     # January 15, 2025
]

# Currency symbols to strip
CURRENCY_SYMBOLS = ["€", "$", "£", "EUR", "USD", "GBP"]

# Patterns for cleaning amounts
AMOUNT_CLEANUP_PATTERN = re.compile(r"[^\d,.\-]")


def normalize_date(
    value: Any,
    output_format: str = "%Y-%m-%d",
) -> str | None:
    """Normalize a date value to ISO format (YYYY-MM-DD).

    Handles multiple input formats commonly used in Portuguese documents.

    Args:
        value: Date value (string, date, or datetime).
        output_format: Desired output format (default ISO).

    Returns:
        Normalized date string, or None if parsing fails.

    Examples:
        >>> normalize_date("15-01-2025")
        '2025-01-15'
        >>> normalize_date("15/01/2025")
        '2025-01-15'
        >>> normalize_date(date(2025, 1, 15))
        '2025-01-15'
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.strftime(output_format)

    if isinstance(value, date):
        return value.strftime(output_format)

    if not isinstance(value, str):
        value = str(value)

    # Clean the string
    clean = value.strip()
    if not clean:
        return None

    # Try each format
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(clean, fmt)
            return parsed.strftime(output_format)
        except ValueError:
            continue

    logger.debug("Failed to parse date", value=value)
    return None


def normalize_amount(
    value: Any,
    decimal_places: int = 2,
) -> str | None:
    """Normalize a monetary amount to standard decimal format.

    Handles European format (comma as decimal separator) and
    US format (period as decimal separator).

    Args:
        value: Amount value (string, int, float, Decimal).
        decimal_places: Number of decimal places in output.

    Returns:
        Normalized amount string (e.g., "1234.56"), or None if parsing fails.

    Examples:
        >>> normalize_amount("1.234,56 €")
        '1234.56'
        >>> normalize_amount("1,234.56")
        '1234.56'
        >>> normalize_amount(1234.56)
        '1234.56'
    """
    if value is None:
        return None

    # Handle numeric types directly
    if isinstance(value, (int, float, Decimal)):
        try:
            return f"{Decimal(str(value)):.{decimal_places}f}"
        except (InvalidOperation, ValueError):
            return None

    if not isinstance(value, str):
        value = str(value)

    # Clean the string
    clean = value.strip()
    if not clean:
        return None

    # Remove currency symbols and whitespace
    for symbol in CURRENCY_SYMBOLS:
        clean = clean.replace(symbol, "")
    clean = clean.strip()

    # Remove any remaining non-numeric characters except . , -
    clean = AMOUNT_CLEANUP_PATTERN.sub("", clean)

    if not clean:
        return None

    # Detect format: European (1.234,56) vs US (1,234.56)
    # European: last separator is comma, dots are thousands
    # US: last separator is period, commas are thousands

    last_comma = clean.rfind(",")
    last_period = clean.rfind(".")

    try:
        if last_comma > last_period:
            # European format: 1.234,56 -> 1234.56
            clean = clean.replace(".", "").replace(",", ".")
        elif last_period > last_comma:
            # US format: 1,234.56 -> 1234.56
            clean = clean.replace(",", "")
        else:
            # No decimal separator or ambiguous
            # If only commas, treat as thousands separators (whole number)
            if "," in clean and "." not in clean:
                clean = clean.replace(",", "")
            # If only periods and looks like thousands (>2 digits after)
            elif "." in clean and "," not in clean:
                parts = clean.split(".")
                if len(parts) == 2 and len(parts[1]) == 3:
                    # Likely thousands separator: 1.234 -> 1234
                    clean = clean.replace(".", "")
                # Otherwise keep as decimal

        result = Decimal(clean)
        return f"{result:.{decimal_places}f}"

    except (InvalidOperation, ValueError) as e:
        logger.debug("Failed to parse amount", value=value, error=str(e))
        return None


def normalize_number(value: Any) -> str | None:
    """Normalize a number (strip units, convert to plain number).

    Useful for metrics like kWh, m3, etc.

    Args:
        value: Number value possibly with units.

    Returns:
        Plain number string, or None if parsing fails.

    Examples:
        >>> normalize_number("123,45 kWh")
        '123.45'
        >>> normalize_number("8 m3")
        '8'
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        # Format without unnecessary decimals
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)

    if not isinstance(value, str):
        value = str(value)

    # Remove common unit suffixes
    units = ["kwh", "kw", "w", "m3", "m2", "m", "kg", "g", "l", "ml", "kva", "%"]
    clean = value.lower().strip()
    for unit in units:
        clean = clean.replace(unit, "").strip()

    # Now normalize as amount (handles decimal separators)
    result = normalize_amount(clean, decimal_places=10)
    if result:
        # Remove trailing zeros and unnecessary decimal point
        result = result.rstrip("0").rstrip(".")
    return result


def normalize_text(value: Any, max_length: int | None = None) -> str | None:
    """Normalize text: strip whitespace, collapse multiple spaces.

    Args:
        value: Text value.
        max_length: Optional maximum length (truncates with ellipsis).

    Returns:
        Cleaned text string, or None if empty.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    # Strip and collapse whitespace
    clean = " ".join(value.split())

    if not clean:
        return None

    if max_length and len(clean) > max_length:
        clean = clean[: max_length - 3] + "..."

    return clean


def normalize_nif(value: Any) -> str | None:
    """Normalize Portuguese NIF (tax ID).

    Args:
        value: NIF value.

    Returns:
        Normalized 9-digit NIF, or None if invalid.

    Examples:
        >>> normalize_nif("123 456 789")
        '123456789'
        >>> normalize_nif("PT123456789")
        '123456789'
    """
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    # Remove everything except digits
    clean = re.sub(r"[^\d]", "", value)

    # Portuguese NIF is 9 digits
    if len(clean) == 9:
        return clean

    # Sometimes prefixed with country code
    if len(clean) == 11 and clean.startswith("351"):
        return clean[3:]

    return None


def normalize_mb_reference(value: Any) -> str | None:
    """Normalize Portuguese Multibanco reference.

    Args:
        value: MB reference value.

    Returns:
        Normalized reference (digits only), or None if invalid.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    # Remove everything except digits
    clean = re.sub(r"[^\d]", "", value)

    # MB references are typically 9 digits (reference) or 15 digits (full)
    if len(clean) in [9, 15]:
        return clean

    return None


def calculate_due_date(
    issue_date: str | date,
    days: int,
    output_format: str = "%Y-%m-%d",
) -> str | None:
    """Calculate due date from issue date.

    Args:
        issue_date: Issue date (string or date object).
        days: Number of days after issue date.
        output_format: Output date format.

    Returns:
        Due date string, or None if calculation fails.
    """
    if isinstance(issue_date, str):
        normalized = normalize_date(issue_date)
        if not normalized:
            return None
        issue_date = datetime.strptime(normalized, "%Y-%m-%d").date()

    due = issue_date + timedelta(days=days)
    return due.strftime(output_format)


def is_empty_value(value: Any) -> bool:
    """Check if a value is considered empty.

    Args:
        value: Any value.

    Returns:
        True if value is None, empty string, or whitespace only.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def values_match(value1: Any, value2: Any, normalize: bool = True) -> bool:
    """Check if two values are equivalent.

    Args:
        value1: First value.
        value2: Second value.
        normalize: Whether to normalize values before comparing.

    Returns:
        True if values are equivalent.
    """
    if is_empty_value(value1) and is_empty_value(value2):
        return True

    if is_empty_value(value1) or is_empty_value(value2):
        return False

    if normalize:
        # Try as amounts
        norm1 = normalize_amount(value1)
        norm2 = normalize_amount(value2)
        if norm1 and norm2:
            return norm1 == norm2

        # Try as dates
        norm1 = normalize_date(value1)
        norm2 = normalize_date(value2)
        if norm1 and norm2:
            return norm1 == norm2

    # String comparison (case-insensitive, whitespace normalized)
    str1 = " ".join(str(value1).lower().split())
    str2 = " ".join(str(value2).lower().split())
    return str1 == str2
