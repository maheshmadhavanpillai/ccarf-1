"""Shared utility functions."""

import re


def validate_account_id(account_id: str) -> bool:
    """Validate that an account ID matches the expected format.

    Args:
        account_id: The ID to validate.

    Returns:
        True if the format is ACC-XXXXX (5 digits).
    """
    return bool(re.match(r"^ACC-\d{5}$", account_id))


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format a numeric amount as a currency string.

    Args:
        amount: The numeric amount.
        currency: ISO 4217 currency code.

    Returns:
        Formatted string like "$1,234.56 USD".
    """
    if currency == "USD":
        return f"${amount:,.2f} USD"
    return f"{amount:,.2f} {currency}"
