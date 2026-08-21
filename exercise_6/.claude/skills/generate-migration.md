---
context: fork
allowed-tools:
  - Bash
  - Read
  - Write
description: "Generate and validate an Alembic database migration based on model changes."
---

# /generate-migration

Generate a database migration from current model changes.

## Steps

1. **Detect model changes**:
   ```bash
   git diff HEAD -- src/models/
   ```

2. **Generate the migration**:
   ```bash
   alembic revision --autogenerate -m "${MIGRATION_MESSAGE}"
   ```

3. **Review the generated migration**:
   - Read the generated file
   - Verify it only contains expected changes
   - Check for destructive operations (DROP TABLE, DROP COLUMN)
   - If destructive: WARN the user and ask for confirmation

4. **Validate migration**:
   ```bash
   alembic upgrade head --sql  # Dry run — generates SQL without executing
   ```

5. **Add safety checks** to the migration:
   - Add `IF EXISTS` to DROP operations
   - Add `IF NOT EXISTS` to CREATE operations
   - Set appropriate lock timeout for ALTER TABLE

## Constraints

- Never execute `alembic upgrade head` against a real database
- Only generate SQL preview (`--sql` flag)
- Flag any migration that takes a lock on tables with >1M rows
- Write access is limited to the `alembic/versions/` directory
