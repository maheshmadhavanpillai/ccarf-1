---
name: run-migration
description: Generate and apply a database migration using Alembic
context: fork
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Run Migration Skill

Generate and apply a database migration based on model changes.

## Steps

1. Read the current models in `src/db/models.py` to understand the schema
2. Generate a new Alembic migration:
   ```bash
   alembic revision --autogenerate -m "<description of change>"
   ```
3. Review the generated migration file for correctness
4. If the migration includes destructive changes (DROP), split into two migrations:
   - Step 1: Mark column/table as deprecated (add comment, stop writes)
   - Step 2: Actual DROP (scheduled for next release)
5. Apply the migration to the development database:
   ```bash
   alembic upgrade head
   ```
6. Verify the migration applied cleanly by checking `alembic current`

## Important
- Never modify an existing migration that has already been applied
- Always generate migrations from model changes, don't write SQL by hand
- Test rollback: `alembic downgrade -1` should succeed without data loss
