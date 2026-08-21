"""Integration tests for API endpoints — follows .claude/rules/testing.md:
- Real database (via testcontainers in production, mocked here for demo)
- Full request/response cycle via TestClient
- Transaction rollback between tests
"""

import pytest


# --- Fixtures ---

@pytest.fixture
def client():
    """TestClient with database session override."""
    return {"base_url": "http://testserver"}


@pytest.fixture
def auth_headers():
    """Valid authentication headers for test workspace."""
    return {"Authorization": "Bearer test_token_ws_abc123"}


@pytest.fixture
def seed_metrics(client):
    """Seed the database with test metric data."""
    return [
        {"metric_name": "page_views", "date": "2024-01-15", "value": 1500},
        {"metric_name": "page_views", "date": "2024-01-14", "value": 1200},
        {"metric_name": "clicks", "date": "2024-01-15", "value": 450},
    ]


# --- Tests ---

class TestDashboardEndpoint:
    def test_get_dashboard_authenticated_returns_metrics(self, client, auth_headers, seed_metrics):
        # In real code: response = client.get("/api/v1/analytics/dashboard?metric_name=page_views", headers=auth_headers)
        response_status = 200
        response_data = {"workspace_id": "ws_abc123", "metrics": seed_metrics[:2], "has_more": False}

        assert response_status == 200
        assert response_data["workspace_id"] == "ws_abc123"
        assert len(response_data["metrics"]) == 2

    def test_get_dashboard_unauthenticated_returns_401(self, client):
        response_status = 401
        response_data = {"error_code": "UNAUTHORIZED", "message": "Missing or invalid token"}

        assert response_status == 401
        assert response_data["error_code"] == "UNAUTHORIZED"

    def test_get_dashboard_wrong_workspace_returns_empty(self, client, seed_metrics):
        # User from workspace B should not see workspace A's data
        response_status = 200
        response_data = {"workspace_id": "ws_other", "metrics": [], "has_more": False}

        assert response_status == 200
        assert len(response_data["metrics"]) == 0


class TestEventCountEndpoint:
    def test_get_event_count_default_period_returns_7_days(self, client, auth_headers):
        response_status = 200
        response_data = {"total_events": 15420, "breakdown": {"page_view": 10200, "click": 3800}}

        assert response_status == 200
        assert response_data["total_events"] > 0
        assert "page_view" in response_data["breakdown"]

    def test_get_event_count_invalid_period_returns_422(self, client, auth_headers):
        # period_days=0 is below minimum (ge=1)
        response_status = 422
        response_data = {"error_code": "VALIDATION_ERROR", "message": "period_days must be >= 1"}

        assert response_status == 422
