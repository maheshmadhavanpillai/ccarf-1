"""Banking API routes — account management endpoints."""

from dataclasses import dataclass
from typing import Any


@dataclass
class APIResponse:
    """Standard API response envelope."""
    success: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


def get_account(account_id: str) -> APIResponse:
    """Retrieve account details by ID.

    Args:
        account_id: The account identifier (format: ACC-XXXXX).

    Returns:
        APIResponse with account data or error details.
    """
    if not account_id.startswith("ACC-"):
        return APIResponse(
            success=False,
            error={
                "code": "INVALID_ACCOUNT_ID",
                "message": "Account ID must start with 'ACC-'",
                "details": {"provided": account_id}
            }
        )

    # In production, this queries the database via repository layer
    return APIResponse(
        success=True,
        data={"account_id": account_id, "balance": 15420.50, "currency": "USD"}
    )


def transfer_funds(
    from_account: str,
    to_account: str,
    amount: float,
    memo: str | None = None
) -> APIResponse:
    """Initiate a fund transfer between accounts.

    Args:
        from_account: Source account ID.
        to_account: Destination account ID.
        amount: Transfer amount in USD (must be positive).
        memo: Optional transfer description.

    Returns:
        APIResponse with transfer confirmation or error.

    Raises:
        ValueError: If amount is not positive.
    """
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")

    if amount > 10000:
        return APIResponse(
            success=False,
            error={
                "code": "ESCALATION_REQUIRED",
                "message": f"Transfers above $10,000 require supervisor approval",
                "details": {"amount": amount, "threshold": 10000}
            }
        )

    return APIResponse(
        success=True,
        data={
            "transfer_id": "TXN-123456",
            "from": from_account,
            "to": to_account,
            "amount": amount,
            "status": "completed"
        }
    )
