---
paths:
  - "src/api/**/*"
---

# API Layer Conventions

## REST Design
- Use standard HTTP methods: GET (read), POST (create), PUT (update), DELETE (remove)
- Resource URLs are plural nouns: `/accounts`, `/transactions`
- Use HTTP status codes correctly: 200 OK, 201 Created, 400 Bad Request, 404 Not Found, 500 Internal Server Error
- Version the API in the URL path: `/v1/accounts`

## Response Format
All API responses MUST follow this envelope structure:

```json
{
  "success": true/false,
  "data": { ... },
  "error": {
    "code": "INSUFFICIENT_FUNDS",
    "message": "Human-readable description",
    "details": {}
  }
}
```

## Authentication
- All endpoints (except /health) require the `authorize_request` middleware
- Use Bearer token authentication in the Authorization header
- Never log or expose tokens in error messages

## Input Validation
- Validate all request body fields using Pydantic models
- Return 400 with specific field errors, not generic "invalid input"
- Sanitize string inputs to prevent injection attacks

## Rate Limiting
- All endpoints must be decorated with `@rate_limit`
- Default: 100 requests/minute per API key
- Document any endpoint-specific overrides in the route docstring
