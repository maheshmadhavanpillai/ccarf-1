# Project: Banking Platform API

## Universal Coding Standards

These rules apply to ALL code in this repository, regardless of location.

### Language & Style
- Python 3.11+ with type hints on all function signatures
- Use `snake_case` for functions/variables, `PascalCase` for classes
- Maximum line length: 100 characters
- Use f-strings for string formatting (never .format() or %)

### Error Handling
- All public functions must handle exceptions explicitly
- Never use bare `except:` — always specify the exception type
- Use structured error responses (see src/api/ conventions for API-specific format)

### Testing Requirements
- Every new feature must include tests before merging
- Minimum 80% code coverage for new modules
- Use pytest as the testing framework
- Tests must be deterministic — no reliance on external services without mocks

### Git Conventions
- Commit messages: imperative mood, max 72 chars for subject line
- Branch naming: `feature/`, `fix/`, `refactor/` prefixes
- All PRs require at least one review

### Security
- Never commit secrets, API keys, or credentials
- Use environment variables for all sensitive configuration
- Validate all external inputs at system boundaries

### Documentation
- Public APIs must have docstrings (Google style)
- Internal functions: only add comments when the "why" is non-obvious
- Keep README.md updated when adding new modules
