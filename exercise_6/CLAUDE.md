# Analytics Platform — Project Standards

## Architecture

This is a SaaS analytics platform with:
- **API layer** (`src/api/`) — FastAPI endpoints serving dashboard data
- **Workers** (`src/workers/`) — Background Celery tasks for data ingestion and aggregation
- **Models** (`src/models/`) — SQLAlchemy ORM models with Alembic migrations
- **Frontend** (`src/frontend/`) — React components consuming the API

## Universal Coding Standards

### Python (Backend)
- Python 3.12+, type hints required on all function signatures
- Use `pydantic` for request/response validation (BaseModel, not raw dicts)
- Async handlers in API layer (`async def`), sync in workers
- Imports: stdlib → third-party → local, separated by blank lines
- No bare `except:` — always catch specific exceptions
- Logging via `structlog` with bound context (not print statements)

### TypeScript (Frontend)
- Strict mode enabled, no `any` types
- React functional components with hooks (no class components)
- State management via Zustand (not Redux)
- API calls through generated OpenAPI client (not raw fetch)

### Testing
- Minimum 80% coverage on new code
- Unit tests for pure logic, integration tests for API endpoints
- Use `pytest` fixtures, never setUp/tearDown methods
- Test file naming: `test_<module>.py` (unit) or `test_<feature>_integration.py`

### Git Conventions
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Branch naming: `<type>/<ticket-id>-<short-description>`
- Squash merge to main, preserve individual commits on feature branches

## Security Requirements

- Never log PII (email, IP, user agent) — use anonymized identifiers
- All database queries via ORM — no raw SQL strings
- API keys and secrets in environment variables only (never in code)
- Rate limiting on all public endpoints (configured in middleware)

## When to Use Plan Mode

Use plan mode (`/plan`) when:
- Adding a new API endpoint (touches routes, models, tests, OpenAPI spec)
- Modifying the data pipeline (workers + models + migrations)
- Any change touching more than 3 files

Execute directly (no plan needed) for:
- Bug fixes in a single file
- Adding/updating tests for existing code
- Documentation updates
- Dependency version bumps
