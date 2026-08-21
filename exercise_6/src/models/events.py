"""SQLAlchemy models for analytics events.

Demonstrates model patterns referenced by .claude/rules/workers.md
(staging → production promotion) and .claude/rules/api-layer.md
(workspace-scoped queries).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """Raw analytics event (staging table)."""
    id: str
    workspace_id: str
    event_type: str
    timestamp: datetime
    properties: dict = field(default_factory=dict)
    user_anonymous_id: str = ""  # Anonymized — never store real user identity
    promoted_at: Optional[datetime] = None


@dataclass
class DailyMetric:
    """Aggregated daily metric (production table, append-only)."""
    id: str
    workspace_id: str
    metric_name: str
    date: str  # YYYY-MM-DD
    value: float
    dimensions: dict = field(default_factory=dict)
    computed_at: datetime = field(default_factory=datetime.now)


@dataclass
class Workspace:
    """Workspace (tenant) model — all queries scoped by this."""
    id: str
    name: str
    plan: str  # "free", "pro", "enterprise"
    created_at: datetime = field(default_factory=datetime.now)
    settings: dict = field(default_factory=dict)
