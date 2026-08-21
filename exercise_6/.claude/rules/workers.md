---
paths:
  - "src/workers/**/*.py"
---

# Worker Rules (Celery Background Tasks)

## Task Design
- Every task must be idempotent (safe to retry on failure)
- Use `bind=True` for access to `self.request` (task ID, retries, etc.)
- Set explicit `max_retries=3` and `default_retry_delay=60`
- Tasks must accept only serializable arguments (no ORM objects, no file handles)

## Error Handling
- Catch specific exceptions, use `self.retry(exc=exc)` for transient failures
- Log structured context on failure: task_id, attempt_number, input_summary
- Dead letter queue: after max_retries, publish to `tasks.dead_letter` for manual review
- Never silently swallow exceptions — always log or re-raise

## Data Pipeline Conventions
- Ingestion tasks write to staging tables first, then promote to production
- Aggregation tasks are append-only (never mutate historical data)
- Use database transactions for multi-table writes
- Chunk large datasets: max 10,000 rows per task execution

## Monitoring
- Every task must emit timing metrics: `task_duration_seconds{task_name=...}`
- Log at INFO level: task start, completion, row counts
- Log at ERROR level: failures with full context
- Use `structlog.bind(task_id=self.request.id)` at task entry
