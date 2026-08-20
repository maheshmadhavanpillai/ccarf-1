"""Database models — SQLAlchemy 2.0 style."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Base:
    """Base model with common fields for all tables."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Account(Base):
    """Bank account model.

    Attributes:
        account_number: External-facing account ID (format: ACC-XXXXX).
        owner_name: Full name of the account holder.
        email: Contact email for notifications.
        balance: Current available balance in USD.
        is_active: Whether the account is open and operational.
    """
    __tablename__ = "accounts"

    account_number: str = ""
    owner_name: str = ""
    email: str = ""
    balance: float = 0.0
    is_active: bool = True


@dataclass
class Transaction(Base):
    """Transaction record model.

    Attributes:
        from_account_id: UUID of the source account.
        to_account_id: UUID of the destination account.
        amount: Transaction amount in USD.
        memo: Optional description.
        status: One of: pending, completed, failed, reversed.
    """
    __tablename__ = "transactions"

    from_account_id: str = ""
    to_account_id: str = ""
    amount: float = 0.0
    memo: str = ""
    status: str = "pending"
