---
paths:
  - "src/db/**/*"
---

# Database Layer Conventions

## ORM & Queries
- Use SQLAlchemy 2.0 style (select() statements, not legacy Query API)
- All queries must go through the repository pattern (no raw SQL in routes)
- Use parameterized queries — never construct SQL with string interpolation

## Models
- All models inherit from `Base` (defined in src/db/base.py)
- Include `created_at` and `updated_at` timestamps on every table
- Use UUID primary keys (not auto-increment integers)
- Define `__tablename__` explicitly on every model

## Migrations
- Use Alembic for all schema changes
- Migration files must be reviewable: include a descriptive message
- Never modify a migration that has been applied to production
- Destructive migrations (DROP TABLE, DROP COLUMN) require a 2-step process:
  1. First migration: stop writing to the column/table
  2. Second migration (next release): drop the column/table

## Transactions
- Use the `@transactional` decorator for operations that need atomicity
- Never hold transactions open across HTTP calls or external service calls
- Always use `async with session.begin():` for explicit transaction boundaries

## Performance
- Add indexes for any column used in WHERE clauses or JOINs
- Use `EXPLAIN ANALYZE` before deploying new queries on large tables
- Prefer batch operations over N+1 individual queries
