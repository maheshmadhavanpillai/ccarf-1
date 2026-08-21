# Exercise 6: Configure Claude Code for a Real Project — Detailed Explanation

## Domains Reinforced
- **Domain 3:** Claude Code Configuration & Workflows
- **Domain 2:** Tool Design & MCP Integration

---

## Overview: The Configuration Hierarchy

Claude Code uses a layered configuration system where each layer adds specificity:

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1: CLAUDE.md (Project Root)                                │
│ • Loaded ALWAYS for every file in the project                   │
│ • Universal standards: language, testing, git conventions        │
│ • "When to use plan mode" guidance                              │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: .claude/rules/*.md (Path-Specific Rules)               │
│ • Loaded ONLY when working on files matching the glob pattern   │
│ • YAML frontmatter: paths: ["src/api/**/*.py"]                  │
│ • Additive: rules layer ON TOP of CLAUDE.md (never override)    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: .claude/skills/*.md (Custom Commands)                  │
│ • Invoked explicitly by user: /run-pipeline, /deploy-preview    │
│ • Frontmatter: context, allowed-tools, description              │
│ • Isolation: context: fork = separate context window            │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: .mcp.json (MCP Server Integration)                     │
│ • External tool servers (postgres, github, sentry)              │
│ • Environment variable expansion: ${DATABASE_URL}               │
│ • Project-scoped: lives in project root                         │
└─────────────────────────────────────────────────────────────────┘
```

### How Layers Combine

When editing `src/api/endpoints.py`, Claude sees:
1. **CLAUDE.md** — Python standards, type hints required, structlog logging
2. **rules/api-layer.md** — Pydantic models, dependency injection, cursor pagination
3. NOT rules/workers.md (wrong path)
4. NOT rules/frontend.md (wrong path)

When editing `src/workers/ingestion.py`, Claude sees:
1. **CLAUDE.md** — Same universal standards
2. **rules/workers.md** — Idempotency, retry config, chunking rules
3. NOT rules/api-layer.md (wrong path)

---

## Step 1: CLAUDE.md — Universal Project Standards

### What it does
CLAUDE.md is loaded for EVERY interaction with the project. It establishes the baseline standards that apply regardless of which file you're editing.

### What belongs in CLAUDE.md

| Include | Don't Include |
|---------|--------------|
| Language versions and tooling | File-specific conventions (use rules/) |
| Universal testing requirements | Implementation details |
| Git conventions | Environment setup steps |
| Security requirements | One-time setup instructions |
| Plan mode guidance | Tool-specific configs (use .mcp.json) |

### Plan Mode Guidance

CLAUDE.md should specify WHEN to use plan mode:

```markdown
## When to Use Plan Mode

Use plan mode (`/plan`) when:
- Adding a new API endpoint (touches routes, models, tests, OpenAPI spec)
- Any change touching more than 3 files

Execute directly (no plan needed) for:
- Bug fixes in a single file
- Adding/updating tests
```

This prevents over-planning (simple fix → just do it) and under-planning (multi-file change → think first).

### Exam Insight

CLAUDE.md is the ONLY configuration that's always loaded. If something must apply everywhere (security rules, language standards), it goes here. If it's path-specific, it goes in rules/.

---

## Step 2: Path-Specific Rules (.claude/rules/)

### What they do
Rules files activate ONLY when Claude is working on files matching their glob pattern. This provides targeted guidance without cluttering the context for unrelated files.

### YAML Frontmatter Syntax

```yaml
---
paths:
  - "src/api/**/*.py"      # All Python files under src/api/
  - "src/api/**/*.ts"      # Also TypeScript files (if any)
---
```

### Glob Pattern Reference

| Pattern | Matches | Doesn't Match |
|---------|---------|--------------|
| `src/api/**/*.py` | `src/api/endpoints.py`, `src/api/v2/routes.py` | `src/workers/task.py` |
| `**/*.test.*` | `tests/unit/test_api.py`, `src/foo.test.ts` | `src/api/routes.py` |
| `src/workers/**/*.py` | `src/workers/ingestion.py` | `src/api/endpoints.py` |
| `src/frontend/**/*.tsx` | `src/frontend/Dashboard.tsx` | `src/frontend/utils.ts` (if .tsx only) |

### Our Four Rules Files

| File | Paths | Purpose |
|------|-------|---------|
| `api-layer.md` | `src/api/**/*.py` | REST conventions, Pydantic models, auth patterns |
| `workers.md` | `src/workers/**/*.py` | Idempotency, retry config, chunking, monitoring |
| `testing.md` | `tests/**/*.py`, `**/*test*.py` | Fixtures, AAA pattern, coverage requirements |
| `frontend.md` | `src/frontend/**/*.tsx`, `*.ts`, `*.css` | React patterns, Zustand, Tailwind, a11y |

### Rules are Additive

Rules NEVER override CLAUDE.md. They ADD specificity:
- CLAUDE.md says "use type hints" → applies everywhere
- api-layer.md ADDS "use Pydantic models for responses" → only in API files

### Exam Insight

Key points for the exam:
1. Rules use **YAML frontmatter** with the `paths:` key
2. Glob patterns follow standard conventions (`**` = any depth, `*` = any segment)
3. Rules are **additive** — they layer on top of CLAUDE.md
4. Multiple paths in one rule file means it activates for ANY matching file
5. A file can match MULTIPLE rules (e.g., `tests/api/test_routes.py` matches both testing.md and potentially api-layer.md if the glob includes `tests/`)

---

## Step 3: Custom Skills (.claude/skills/)

### What they do
Skills are user-invokable commands (like `/run-pipeline`) that execute a specific workflow. They have their own context and tool restrictions.

### Frontmatter Options

```yaml
---
context: fork              # Separate context window (doesn't pollute main conversation)
allowed-tools:             # ONLY these tools are available
  - Bash
  - Read
  - Write
description: "..."         # Shown in skill list / help
---
```

### context: fork

| Setting | Behavior |
|---------|----------|
| `context: fork` | Skill runs in a SEPARATE context window. Cannot see or pollute the main conversation. Ideal for autonomous workflows. |
| (no context setting) | Skill runs in the SAME context as the conversation. Can reference what was discussed. |

### allowed-tools Restriction

This is a **hard guardrail** — the skill CANNOT use tools not in its list, regardless of what the prompt says.

| Skill | Allowed Tools | Why |
|-------|--------------|-----|
| `/run-pipeline` | Bash, Read, Edit, Write | Needs to run tests and modify pipeline files |
| `/deploy-preview` | Bash, Read | Can deploy (bash) and read code, but CANNOT modify code |
| `/generate-migration` | Bash, Read, Write | Can generate files and run alembic, but scoped to migrations |

### Security Through Tool Restriction

`/deploy-preview` has no Write or Edit tool:
- It can READ code to understand what's being deployed
- It can RUN bash commands to deploy
- It CANNOT MODIFY code before deploying
- This prevents "fix the bug and deploy" in one step (forces proper review)

### Our Three Skills

| Skill | Context | Tools | Purpose |
|-------|---------|-------|---------|
| `/run-pipeline` | fork | Bash, Read, Edit, Write | Test data pipeline locally |
| `/deploy-preview` | fork | Bash, Read | Deploy preview (read-only code access) |
| `/generate-migration` | fork | Bash, Read, Write | Generate Alembic migration safely |

### Exam Insight

Skills demonstrate two key concepts:
1. **`context: fork`** = isolation. The skill doesn't see the conversation and can't leak information from it.
2. **`allowed-tools`** = hard guardrail. Cannot be bypassed by prompt injection. If Write isn't in the list, the skill CANNOT write files, period.

---

## Step 4: MCP Server Configuration (.mcp.json)

### What it does
`.mcp.json` registers external tool servers that Claude can use for the project. Each server provides specialized capabilities (database queries, GitHub operations, error tracking).

### File Structure

```json
{
  "mcpServers": {
    "server-name": {
      "command": "executable",
      "args": ["arg1", "arg2"],
      "env": {
        "VAR_NAME": "${LOCAL_ENV_VAR}"
      }
    }
  }
}
```

### Environment Variable Expansion

The `${VAR_NAME}` syntax pulls values from the user's local environment:

```json
"env": {
  "POSTGRES_URL": "${DATABASE_URL}"
}
```

This means:
- The `.mcp.json` file is safe to commit to git (no secrets)
- Each developer sets their own `DATABASE_URL` locally
- The MCP server receives the resolved value at runtime

### Our Three MCP Servers

| Server | Purpose | Environment Variables |
|--------|---------|---------------------|
| `postgres` | Query database schema, inspect tables, run read-only SQL | `${DATABASE_URL}` |
| `github` | Create PRs, read issues, check CI status | `${GITHUB_TOKEN}` |
| `sentry` | Look up errors, check error rates, find regressions | `${SENTRY_AUTH_TOKEN}`, `${SENTRY_ORG}` |

### How MCP Servers Enhance Claude

Without MCP servers, Claude can only read/write local files and run bash commands. With them:

| Task | Without MCP | With MCP |
|------|------------|----------|
| Check database schema | Read migration files (may be outdated) | Query live schema directly |
| Find related issues | User must paste issue text | Claude searches GitHub issues |
| Investigate errors | User must describe the error | Claude queries Sentry for stack traces |

### Security Considerations

1. **Secrets stay local** — `${VAR}` expansion means tokens never appear in committed files
2. **Project-scoped** — `.mcp.json` at project root means these servers are only available for THIS project
3. **Server trust** — MCP servers are external processes; only use trusted, audited servers
4. **Read vs write** — Some servers (like postgres) should be configured read-only in development

### Exam Insight

MCP configuration in `.mcp.json`:
1. Uses `${ENV_VAR}` syntax for secret expansion (safe to commit)
2. Each server is an external process spawned by Claude Code
3. Servers provide domain-specific tools (database, GitHub, monitoring)
4. Project-scoped: different projects can have different MCP servers
5. The `command` + `args` pattern lets you use any MCP-compatible server

---

## Step 5: How the Hierarchy Works Together

### Scenario: Adding a New API Endpoint

```
User: "Add a GET /api/v1/analytics/funnel endpoint"
```

1. **CLAUDE.md loads** → knows Python 3.12, type hints, structlog, plan mode triggers
2. **Plan mode activates** (new endpoint = multi-file change per CLAUDE.md guidance)
3. Claude creates a plan touching: `src/api/endpoints.py`, `src/models/`, `tests/`
4. **When editing `src/api/endpoints.py`:**
   - rules/api-layer.md activates → Pydantic model, dependency injection, cursor pagination
5. **When editing `tests/integration/test_api_integration.py`:**
   - rules/testing.md activates → pytest fixtures, AAA pattern, real database
6. **MCP postgres server** → Claude checks current table schema before writing queries
7. **After implementation, user runs `/generate-migration`:**
   - Skill forks context, uses Bash+Read+Write
   - Generates Alembic migration, validates with `--sql` flag
   - Returns result to user

### Scenario: Debugging a Worker Failure

```
User: "The daily aggregation task is failing"
```

1. **CLAUDE.md loads** → universal standards
2. **When reading `src/workers/ingestion.py`:**
   - rules/workers.md activates → idempotency, retry patterns, structured logging
3. **MCP sentry server** → Claude queries Sentry for the actual error/stack trace
4. **MCP github server** → Claude checks if there's an existing issue for this error
5. Claude fixes the bug (single file → no plan mode needed per CLAUDE.md)
6. **User runs `/run-pipeline`:**
   - Skill forks context, validates DATABASE_URL is local
   - Runs pipeline in eager mode, validates output

---

## Project Structure Reference

```
exercise_6/
├── CLAUDE.md                              # Layer 1: Universal standards
├── .claude/
│   ├── rules/
│   │   ├── api-layer.md                   # Layer 2: paths: ["src/api/**/*.py"]
│   │   ├── workers.md                     # Layer 2: paths: ["src/workers/**/*.py"]
│   │   ├── testing.md                     # Layer 2: paths: ["tests/**/*.py", "**/*test*.py"]
│   │   └── frontend.md                    # Layer 2: paths: ["src/frontend/**/*.tsx", ...]
│   └── skills/
│       ├── run-pipeline.md                # Layer 3: context: fork, tools: Bash,Read,Edit,Write
│       ├── deploy-preview.md              # Layer 3: context: fork, tools: Bash,Read (NO Write!)
│       └── generate-migration.md          # Layer 3: context: fork, tools: Bash,Read,Write
├── .mcp.json                              # Layer 4: postgres, github, sentry servers
├── src/
│   ├── api/endpoints.py                   # Triggers: CLAUDE.md + api-layer.md
│   ├── workers/ingestion.py               # Triggers: CLAUDE.md + workers.md
│   ├── models/events.py                   # Triggers: CLAUDE.md only
│   └── frontend/Dashboard.tsx             # Triggers: CLAUDE.md + frontend.md
└── tests/
    ├── unit/test_ingestion.py             # Triggers: CLAUDE.md + testing.md
    └── integration/test_api_integration.py # Triggers: CLAUDE.md + testing.md
```

---

## Key Takeaways for the Exam

1. **CLAUDE.md is always loaded** — it's the universal baseline. Put language standards, security rules, and plan mode guidance here. Never put path-specific rules in CLAUDE.md.

2. **Rules use YAML frontmatter globs** — `paths: ["src/api/**/*.py"]` means the rule only activates for files matching that pattern. Multiple paths in one rule = OR logic. Multiple rules matching one file = all load (additive).

3. **Skills have three key frontmatter fields:**
   - `context: fork` — isolates the skill in its own context window
   - `allowed-tools` — hard restriction on what tools the skill can use (cannot be prompt-injected)
   - `description` — shown in skill listing

4. **`allowed-tools` is a hard guardrail** — if Write isn't listed, the skill cannot write files regardless of what the prompt says. This is code-level enforcement, not prompt-level.

5. **`.mcp.json` uses `${ENV_VAR}` expansion** — secrets stay in the developer's environment, the config file is safe to commit. Each developer resolves their own values.

6. **The hierarchy is additive, not overriding:**
   - CLAUDE.md → base rules
   - + matching rules/ → add specificity
   - + skills/ → separate workflows with restrictions
   - + .mcp.json → external tool access

7. **Plan mode guidance belongs in CLAUDE.md** — tell Claude WHEN to plan (multi-file changes) vs. execute directly (single-file fixes). This prevents both over-planning and under-planning.

8. **MCP servers are project-scoped** — different projects can have different external tools. A data project might have a postgres MCP server; a frontend project might have a Figma MCP server.

9. **Skills can restrict access for safety:**
   - `/deploy-preview` has NO Write access → can't modify code before deploying
   - `/generate-migration` has Write access → but skill instructions limit it to `alembic/versions/`

10. **Configuration is checked into git** — CLAUDE.md, rules/, skills/, and .mcp.json are all committable. Secrets use `${ENV_VAR}` expansion. This means the ENTIRE team shares the same Claude configuration.
