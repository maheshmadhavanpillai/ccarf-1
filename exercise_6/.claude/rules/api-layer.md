---
paths:
  - "src/api/**/*.py"
  - "src/api/**/*.ts"
---

# API Layer Rules

## Endpoint Design
- All endpoints return Pydantic response models (never raw dicts)
- Use dependency injection for auth, database sessions, and rate limiting
- Path parameters for resource IDs, query parameters for filtering/pagination
- Pagination: cursor-based for large datasets, offset-based only for admin views

## Error Responses
- Always use the standard `APIError` response model:
  ```python
  class APIError(BaseModel):
      error_code: str        # Machine-readable: "RATE_LIMITED", "NOT_FOUND"
      message: str           # Human-readable explanation
      details: dict | None   # Optional context (validation errors, retry-after)
  ```
- HTTP status codes: 400 (validation), 401 (auth), 403 (permission), 404 (not found), 429 (rate limit), 500 (internal)

## Authentication
- All endpoints require `Authorization: Bearer <token>` header
- Use `Depends(get_current_user)` — never parse tokens manually
- Workspace-scoped: every query must filter by `workspace_id` from the token

## Performance
- Database queries must use `.select_related()` or explicit joins (no N+1)
- Response time budget: p99 < 200ms for dashboard endpoints
- Use `@cache_response(ttl=60)` decorator for read-heavy endpoints
- Background heavy computation — return 202 Accepted with a job ID

## OpenAPI Documentation
- Every endpoint must have a docstring (becomes the OpenAPI description)
- Include `response_model`, `status_code`, and `tags` in the decorator
- Example values in Pydantic models via `model_config = {"json_schema_extra": {...}}`
