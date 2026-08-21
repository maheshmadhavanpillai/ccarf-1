---
context: fork
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
description: "Run a data pipeline task locally for testing. Executes the Celery worker in eager mode and validates output."
---

# /run-pipeline

Run a data pipeline task locally for testing and validation.

## Steps

1. **Read the task file** to understand the pipeline being tested
2. **Check for required environment variables** (DATABASE_URL, REDIS_URL)
3. **Run the task in eager mode** (synchronous, no broker needed):
   ```bash
   CELERY_ALWAYS_EAGER=1 python -m pytest tests/integration/test_pipeline.py -v
   ```
4. **Validate the output**:
   - Check staging tables have expected row counts
   - Verify no duplicate records
   - Confirm metrics were emitted
5. **Report results** with timing and row counts

## Important

- NEVER run against production database
- Always check DATABASE_URL starts with `postgresql://localhost` or `postgresql://test`
- If DATABASE_URL points to a non-local host, STOP and alert the user
- Maximum execution time: 60 seconds (kill if exceeded)
