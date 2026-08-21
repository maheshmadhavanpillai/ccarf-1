"""Analytics dashboard API endpoints.

These endpoints follow the rules defined in .claude/rules/api-layer.md:
- Pydantic response models (not raw dicts)
- Dependency injection for auth and database
- Cursor-based pagination for large datasets
- Standard APIError responses
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# --- Response Models (Pydantic) ---

class APIError(BaseModel):
    error_code: str
    message: str
    details: dict | None = None


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float
    dimension: str | None = None


class DashboardResponse(BaseModel):
    workspace_id: str
    metrics: list[MetricPoint]
    cursor: str | None = None
    has_more: bool = False

    model_config = {"json_schema_extra": {
        "example": {
            "workspace_id": "ws_abc123",
            "metrics": [{"timestamp": "2024-01-15T10:00:00Z", "value": 42.5, "dimension": "page_views"}],
            "cursor": "eyJpZCI6IDEwMH0=",
            "has_more": True,
        }
    }}


class EventCountResponse(BaseModel):
    total_events: int
    period_start: datetime
    period_end: datetime
    breakdown: dict[str, int] = Field(default_factory=dict)


# --- Dependencies ---

async def get_current_user():
    """Extract and validate user from Bearer token."""
    return {"user_id": "usr_123", "workspace_id": "ws_abc123"}


async def get_db_session():
    """Provide a database session with automatic cleanup."""
    return {"session": "mock_session"}


# --- Endpoints ---

@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    status_code=200,
)
async def get_dashboard_metrics(
    user=Depends(get_current_user),
    db=Depends(get_db_session),
    metric_name: str = Query(..., description="Metric to retrieve"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
):
    """Retrieve dashboard metrics for the current workspace.

    Returns time-series data points with cursor-based pagination.
    All queries are scoped to the authenticated user's workspace.
    """
    workspace_id = user["workspace_id"]

    return DashboardResponse(
        workspace_id=workspace_id,
        metrics=[
            MetricPoint(timestamp=datetime(2024, 1, 15, 10, 0), value=42.5, dimension=metric_name),
            MetricPoint(timestamp=datetime(2024, 1, 15, 11, 0), value=55.2, dimension=metric_name),
        ],
        cursor="eyJpZCI6IDEwMH0=",
        has_more=True,
    )


@router.get(
    "/events/count",
    response_model=EventCountResponse,
    status_code=200,
)
async def get_event_count(
    user=Depends(get_current_user),
    db=Depends(get_db_session),
    period_days: int = Query(7, ge=1, le=90, description="Lookback period in days"),
):
    """Count events in the specified period, broken down by event type.

    Scoped to the authenticated user's workspace.
    """
    now = datetime(2024, 1, 15, 12, 0)
    start = datetime(2024, 1, 8, 12, 0)

    return EventCountResponse(
        total_events=15420,
        period_start=start,
        period_end=now,
        breakdown={"page_view": 10200, "click": 3800, "form_submit": 1420},
    )
