---
paths:
  - "tests/**/*.py"
  - "**/*test*.py"
  - "**/*_test.py"
---

# Testing Rules

## Test Structure
- Use `pytest` with fixtures (no unittest.TestCase subclasses)
- Arrange-Act-Assert pattern with blank lines between sections
- One assertion per test (or closely related group of assertions)
- Test names: `test_<action>_<scenario>_<expected_result>`

## Fixtures
- Database fixtures use `@pytest.fixture` with `session` scope for expensive setup
- Use factory functions (`create_user(...)`) not raw ORM inserts in tests
- Clean up: use transaction rollback (`autouse=True` fixture), not DELETE statements
- Shared fixtures in `conftest.py` at the appropriate directory level

## Unit Tests (`tests/unit/`)
- No database, no network, no filesystem
- Mock external dependencies with `unittest.mock.patch`
- Test pure logic: calculations, transformations, validation rules
- Fast: entire unit suite must complete in < 10 seconds

## Integration Tests (`tests/integration/`)
- Use real database (PostgreSQL via testcontainers or docker-compose)
- Test full request/response cycle via `TestClient`
- Seed data via fixtures, not by calling other endpoints
- Clean database between tests (transaction rollback)

## Coverage
- Minimum 80% on new code (enforced in CI)
- 100% coverage on critical paths: auth, billing, data deletion
- Exclude from coverage: migration files, generated code, type stubs

## What NOT to Test
- Don't test framework behavior (FastAPI routing, SQLAlchemy queries)
- Don't test third-party libraries
- Don't write tests that only assert the mock was called (test behavior, not implementation)
