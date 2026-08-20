"""Tests for banking API routes."""

import pytest
from src.api.routes import get_account, transfer_funds, APIResponse


class TestGetAccount:
    """Tests for the get_account endpoint."""

    def test_get_account_valid_id_returns_balance(self):
        result = get_account("ACC-12345")

        assert result.success is True
        assert result.data["account_id"] == "ACC-12345"
        assert result.data["balance"] == 15420.50
        assert result.data["currency"] == "USD"

    def test_get_account_invalid_format_returns_error(self):
        result = get_account("INVALID-123")

        assert result.success is False
        assert result.error["code"] == "INVALID_ACCOUNT_ID"
        assert "ACC-" in result.error["message"]


class TestTransferFunds:
    """Tests for the transfer_funds endpoint."""

    def test_transfer_within_limit_succeeds(self):
        result = transfer_funds("ACC-12345", "ACC-67890", 500.00)

        assert result.success is True
        assert result.data["status"] == "completed"
        assert result.data["amount"] == 500.00

    def test_transfer_above_threshold_requires_escalation(self):
        result = transfer_funds("ACC-12345", "ACC-67890", 15000.00)

        assert result.success is False
        assert result.error["code"] == "ESCALATION_REQUIRED"
        assert result.error["details"]["threshold"] == 10000

    def test_transfer_negative_amount_raises_error(self):
        with pytest.raises(ValueError, match="must be positive"):
            transfer_funds("ACC-12345", "ACC-67890", -100.00)

    def test_transfer_zero_amount_raises_error(self):
        with pytest.raises(ValueError, match="must be positive"):
            transfer_funds("ACC-12345", "ACC-67890", 0)
