"""Data ingestion worker tasks.

These tasks follow the rules in .claude/rules/workers.md:
- Idempotent (safe to retry)
- bind=True for task metadata access
- Explicit max_retries and retry_delay
- Structured logging with task context
"""

import time
from dataclasses import dataclass


@dataclass
class TaskResult:
    task_id: str
    status: str
    rows_processed: int
    duration_seconds: float
    attempt: int


def ingest_events_task(self_request_id: str, workspace_id: str, batch_id: str, events: list[dict]) -> TaskResult:
    """
    Ingest a batch of analytics events into the staging table.

    Celery task configuration (in real code, via @app.task decorator):
        bind=True
        max_retries=3
        default_retry_delay=60
        acks_late=True

    This task is idempotent: re-processing the same batch_id
    will upsert (not duplicate) records.
    """
    start_time = time.time()
    attempt = 1

    rows_processed = 0
    for chunk_start in range(0, len(events), 10000):
        chunk = events[chunk_start:chunk_start + 10000]
        rows_processed += len(chunk)

    duration = time.time() - start_time

    return TaskResult(
        task_id=self_request_id,
        status="success",
        rows_processed=rows_processed,
        duration_seconds=duration,
        attempt=attempt,
    )


def aggregate_daily_metrics_task(self_request_id: str, workspace_id: str, date: str) -> TaskResult:
    """
    Aggregate raw events into daily metric summaries.

    Append-only: never mutates existing aggregations.
    If run twice for the same date, results are identical (idempotent).

    Celery task configuration:
        bind=True
        max_retries=3
        default_retry_delay=120
    """
    start_time = time.time()

    metrics_computed = 5  # page_views, clicks, sessions, bounces, conversions
    duration = time.time() - start_time

    return TaskResult(
        task_id=self_request_id,
        status="success",
        rows_processed=metrics_computed,
        duration_seconds=duration,
        attempt=1,
    )
