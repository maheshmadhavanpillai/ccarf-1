---
paths:
  - "**/*.test.*"
  - "tests/**/*"
---

# Testing Conventions

## Framework & Structure
- Use pytest with pytest-asyncio for async tests
- One test file per source module (e.g., routes.py → routes.test.py)
- Group related tests in classes: `class TestAccountCreation:`

## Naming
- Test functions: `test_<action>_<scenario>_<expected_result>`
- Example: `test_transfer_insufficient_funds_returns_400`
- Fixtures: descriptive names like `authenticated_client`, `sample_account`

## Fixtures & Setup
- Use pytest fixtures (not setUp/tearDown methods)
- Prefer factory fixtures over static data: `make_account(balance=1000)`
- Scope fixtures appropriately: `session` for DB, `function` for state

## Assertions
- One logical assertion per test (multiple asserts on the same object is fine)
- Use pytest's built-in assertions, not unittest's self.assert*
- For API tests, always check both status code AND response body

## Mocking
- Mock external services (HTTP calls, email, SMS) — always
- Mock the database — never (use a test database instead)
- Use `pytest-mock`'s `mocker` fixture, not `unittest.mock.patch` directly

## Coverage
- New code must have >80% line coverage
- Critical paths (money movement, auth) must have 100% branch coverage
- Run with: `pytest --cov=src --cov-report=term-missing`
