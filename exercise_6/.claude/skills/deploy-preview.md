---
context: fork
allowed-tools:
  - Bash
  - Read
description: "Deploy a preview environment for the current branch. Read-only access to code, bash for deployment commands."
---

# /deploy-preview

Deploy a preview environment for the current feature branch.

## Steps

1. **Verify branch state**:
   - Must be on a feature branch (not main/master)
   - All changes must be committed (no dirty working tree)
   - Branch must be pushed to remote

2. **Run pre-deploy checks**:
   ```bash
   python -m pytest tests/unit/ -x --timeout=30
   python -m mypy src/ --strict
   ```

3. **Deploy to preview**:
   ```bash
   flyctl deploy --app analytics-preview-${BRANCH_NAME} --remote-only
   ```

4. **Verify deployment**:
   ```bash
   curl -sf https://analytics-preview-${BRANCH_NAME}.fly.dev/health
   ```

5. **Report** the preview URL and deployment status

## Constraints

- This skill has NO Write/Edit access — it cannot modify code
- If tests fail, report the failure and stop (do not deploy broken code)
- Preview environments auto-destroy after 24 hours
