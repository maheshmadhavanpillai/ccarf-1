# Exercise 2: Configure Claude Code for a Team Development Workflow — Detailed Explanation

## Domains Reinforced
- **Domain 3:** Claude Code Configuration & Workflows
- **Domain 2:** Tool Design & MCP Integration

---

## Step 1: Project-Level CLAUDE.md

### What it does
`CLAUDE.md` at the project root defines **universal rules** that apply to every file in the repository. Every developer using Claude Code in this project will have these instructions loaded automatically.

### How it works

```
CLAUDE.md (project root)
    │
    ├── Applied when Claude Code is launched in this directory
    ├── Loaded for ALL file edits, regardless of path
    └── Acts as the "constitution" for the project
```

**Key design decisions in our CLAUDE.md:**

| Section | Why it's there |
|---------|---------------|
| Language & Style | Ensures consistent code style across all developers |
| Error Handling | Prevents bare `except:` and sloppy error patterns |
| Testing Requirements | Enforces quality gate (80% coverage, pytest) |
| Git Conventions | Standardizes commit messages and branching |
| Security | Hard rules that prevent credential leaks |

### The Configuration Hierarchy

Claude Code loads instructions in this order (later overrides earlier):

```
~/.claude/CLAUDE.md          ← User-level (personal preferences)
    ↓
./CLAUDE.md                  ← Project-level (team standards)  ← WE ARE HERE
    ↓
./.claude/rules/*.md         ← Path-specific (contextual rules)
    ↓
Conversation context         ← Runtime additions
```

**Exam insight:** Project-level CLAUDE.md is the "single source of truth" for team conventions. It's version-controlled (committed to git), so all team members share the same rules. User-level `~/.claude/CLAUDE.md` is for personal preferences (e.g., "I prefer verbose explanations") that shouldn't be imposed on the team.

---

## Step 2: Path-Specific Rules (.claude/rules/)

### What it does
Files in `.claude/rules/` use **YAML frontmatter with glob patterns** to apply rules ONLY when Claude Code is working on matching files. This gives you contextual conventions without cluttering every interaction.

### How it works

```yaml
---
paths:
  - "src/api/**/*"      ← Glob pattern: matches any file under src/api/
---

# Rules content here (only loaded for matching files)
```

### Our Three Rule Files

| File | Glob Pattern | When it activates |
|------|-------------|-------------------|
| `api-conventions.md` | `src/api/**/*` | Editing routes.py, middleware.py, etc. |
| `testing-conventions.md` | `**/*.test.*`, `tests/**/*` | Editing any test file |
| `database-conventions.md` | `src/db/**/*` | Editing models, repositories, migrations |

### Glob Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `*` | Any single filename segment |
| `**` | Any number of directories (recursive) |
| `src/api/**/*` | All files in src/api/ at any depth |
| `**/*.test.*` | Any file with ".test." in its name, anywhere |

### Why Path-Specific Rules Matter

Without them, you'd have two bad options:
1. **Put everything in CLAUDE.md** → Claude gets overwhelmed with irrelevant context (DB rules when editing a test file)
2. **Leave it out** → No contextual guidance for specialized areas

Path-specific rules solve this by being **loaded only when relevant**. This is a Context Management pattern (Domain 5) — give the model only the context it needs for the current task.

### Testing Rule Activation

To verify rules load correctly:
- Edit `src/api/routes.py` → API conventions should apply (REST format, response envelope)
- Edit `tests/api/routes.test.py` → Testing conventions should apply (pytest fixtures, assertion style)
- Edit `src/db/models.py` → Database conventions should apply (SQLAlchemy 2.0, UUID keys)

---

## Step 3: Custom Skill with Fork Context (.claude/skills/)

### What it does
A custom **skill** (slash command) that runs database migrations. The key feature: `context: fork` means it runs in an isolated sub-conversation that doesn't pollute the main chat.

### The Skill File Structure

```yaml
---
name: run-migration           ← Invoked as /run-migration
description: Generate and apply a database migration using Alembic
context: fork                 ← CRITICAL: runs in isolation
allowed-tools:                ← CRITICAL: restricts available tools
  - Bash
  - Read
  - Edit
  - Write
---

# Instructions for the skill (markdown body)
```

### Key Frontmatter Fields

| Field | Purpose |
|-------|---------|
| `name` | The slash command name (`/run-migration`) |
| `description` | Shown in skill listings, helps Claude decide when to suggest it |
| `context: fork` | Runs in a separate context — results don't clutter main conversation |
| `allowed-tools` | Security restriction — only these tools can be used |

### Why `context: fork` Matters

```
Main Conversation                    Forked Skill Context
─────────────────                    ────────────────────
User: "Add email field to Account"
Claude: "I'll update the model..."
User: "/run-migration"
                          ─────────► [Isolated execution]
                                     - Reads models
                                     - Generates migration
                                     - Applies migration
                          ◄───────── [Returns summary only]
Claude: "Migration applied: added
  email column to accounts table"
```

Without fork:
- The entire migration process (file reads, bash output, etc.) fills the main conversation
- This wastes context window on ephemeral operational details
- The main conversation loses track of the higher-level goal

With fork:
- The skill runs in its own context
- Only the final result/summary comes back
- Main conversation stays focused

### Why `allowed-tools` Matters

This is a **security pattern**. The migration skill:
- CAN: Read files, edit files, run bash commands (needed for Alembic)
- CANNOT: Make web requests, call MCP servers, or access tools not listed

This follows the **principle of least privilege** — the skill only gets the tools it actually needs.

---

## Step 4: MCP Server Configuration (.mcp.json)

### What it does
`.mcp.json` configures **MCP (Model Context Protocol) servers** that provide Claude with additional tools — in our case, database access and filesystem operations.

### The Configuration

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_URL": "${POSTGRES_URL}"     ← Environment variable expansion
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./src", "./tests"],
      "env": {}
    }
  }
}
```

### How MCP Servers Work

```
┌─────────────┐     stdio/SSE      ┌──────────────────┐
│ Claude Code │ ◄──────────────────► │ MCP Server       │
│ (client)    │     JSON-RPC        │ (e.g., postgres) │
└─────────────┘                     └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │ Actual Resource   │
                                    │ (PostgreSQL DB)   │
                                    └──────────────────┘
```

1. Claude Code launches the MCP server as a subprocess
2. Communication happens via JSON-RPC over stdio
3. The server exposes **tools** (like `query`, `list_tables`) that Claude can call
4. Claude treats MCP tools the same as built-in tools

### Environment Variable Expansion

```json
"POSTGRES_URL": "${POSTGRES_URL}"
```

This is critical for security:
- The actual database URL (with password) lives in the developer's environment
- It's NOT committed to git
- Each developer can have a different database (local dev vs. staging)
- CI/CD can inject its own value

### Project vs. Personal MCP Servers

| Location | Scope | Use case |
|----------|-------|----------|
| `.mcp.json` (project root) | Shared by all team members | Project database, shared services |
| `~/.claude.json` | Personal, per-developer | Experimental servers, personal tools |

Both are loaded simultaneously — a developer gets BOTH project servers AND their personal ones.

**Example personal config (`~/.claude.json`):**

```json
{
  "mcpServers": {
    "my-experimental-rag": {
      "command": "python",
      "args": ["/Users/me/tools/rag_server.py"],
      "env": {
        "OPENAI_KEY": "${OPENAI_KEY}"
      }
    }
  }
}
```

This server is available ONLY to you, not to other team members. It coexists with the project's postgres and filesystem servers.

---

## Step 5: Plan Mode vs. Direct Execution

### What it does
Claude Code has two execution modes. Choosing the right one depends on task complexity.

### When to Use Each Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Single-file bug fix | **Direct execution** | The fix is localized, low risk, easy to verify |
| Multi-file library migration | **Plan mode** | Need to understand scope, sequence changes, avoid breaking dependencies |
| New feature with multiple approaches | **Plan mode** | Need to evaluate tradeoffs, get alignment before coding |

### Plan Mode Flow

```
User: "Migrate from requests to httpx"

Plan Mode Activated:
┌────────────────────────────────────────┐
│ 1. EXPLORE: Find all usages of requests│
│    - grep for imports                  │
│    - identify patterns used            │
│    - check for async vs sync           │
│                                        │
│ 2. DESIGN: Plan the migration          │
│    - Map requests patterns → httpx     │
│    - Identify breaking changes         │
│    - Sequence the file changes         │
│                                        │
│ 3. PRESENT: Show plan to user          │
│    - "Here's my approach..."           │
│    - "12 files affected..."            │
│    - "Should I proceed?"               │
└────────────────────────────────────────┘

User: "Looks good, go ahead"

Direct Execution:
┌────────────────────────────────────────┐
│ Execute the plan step by step          │
│ Edit files, run tests, verify          │
└────────────────────────────────────────┘
```

### Three Test Scenarios

**Scenario A: Single-file bug fix (Direct execution)**
- Task: "Fix the off-by-one error in `validate_account_id`"
- Why direct: One file, one function, clear fix, easy to verify
- Plan mode adds unnecessary overhead here

**Scenario B: Multi-file library migration (Plan mode)**
- Task: "Migrate from SQLAlchemy 1.x to 2.0 style queries"
- Why plan: Touches many files, has a specific pattern to apply, risk of breaking changes
- Plan mode lets you scope the work and sequence it safely

**Scenario C: New feature with multiple valid approaches (Plan mode)**
- Task: "Add real-time notifications for large transfers"
- Why plan: Could use WebSockets, SSE, polling, or push notifications
- Plan mode lets Claude present options and get alignment before coding

### Exam Insight

Plan mode is valuable when:
1. **Scope is uncertain** — you need to explore before committing
2. **Risk is high** — mistakes are expensive to undo
3. **Multiple approaches exist** — you need user buy-in on direction
4. **Coordination is needed** — changes span multiple files/systems

---

## Architecture Summary: How All Pieces Fit Together

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLAUDE CODE SESSION                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ CLAUDE.md (Project Root)                                 │     │
│  │ Universal rules: style, testing, security, git           │     │
│  │ Applied to: ALL files, ALL developers                    │     │
│  └─────────────────────────────────────────────────────────┘     │
│                          │                                        │
│              ┌───────────┼───────────┐                           │
│              ▼           ▼           ▼                            │
│  ┌───────────────┐ ┌──────────┐ ┌──────────────┐                │
│  │.claude/rules/ │ │.claude/  │ │.claude/      │                │
│  │               │ │rules/    │ │rules/        │                │
│  │api-conventions│ │testing-  │ │database-     │                │
│  │               │ │conventions│ │conventions  │                │
│  │Activates for: │ │          │ │             │                │
│  │src/api/**/*   │ │**/*.test.*│ │src/db/**/* │                │
│  └───────────────┘ └──────────┘ └──────────────┘                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ .claude/skills/run-migration.md                          │     │
│  │ Invoked with: /run-migration                             │     │
│  │ Runs in: forked context (isolated)                       │     │
│  │ Tools allowed: Bash, Read, Edit, Write only              │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ MCP Servers (loaded from .mcp.json + ~/.claude.json)     │     │
│  │                                                           │     │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐    │     │
│  │  │  postgres   │  │  filesystem  │  │ personal-rag │    │     │
│  │  │  (project)  │  │  (project)   │  │ (~/.claude)  │    │     │
│  │  │  ${POSTGRES │  │  ./src,      │  │ personal     │    │     │
│  │  │    _URL}    │  │  ./tests     │  │ experimental │    │     │
│  │  └─────────────┘  └──────────────┘  └──────────────┘    │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ Execution Mode                                           │     │
│  │  • Direct: simple, localized, low-risk tasks             │     │
│  │  • Plan: complex, multi-file, multi-approach tasks       │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways for the Exam

1. **CLAUDE.md hierarchy = cascading configuration** — project-level for team standards, user-level for personal preferences. Project-level is version-controlled.

2. **Path-specific rules reduce context noise** — only load rules relevant to the current file. This is both a UX optimization and a context window optimization.

3. **Glob patterns in YAML frontmatter** are the mechanism for path matching. Know the syntax: `*` (single segment), `**` (recursive), and combinations.

4. **`context: fork` isolates skill execution** — keeps the main conversation clean. This is a Context Management pattern.

5. **`allowed-tools` enforces least privilege** — skills only get the tools they need. This is a security pattern.

6. **MCP servers use environment variable expansion** — credentials never go in config files committed to git. `${VAR_NAME}` syntax.

7. **Project .mcp.json + personal ~/.claude.json coexist** — team tools and personal tools are available simultaneously without conflict.

8. **Plan mode vs. direct execution** is about task complexity. Plan mode adds value when scope is uncertain, risk is high, or multiple approaches exist. Don't use it for simple fixes.

9. **MCP transport** — servers communicate via JSON-RPC over stdio (local) or SSE (remote). Claude Code launches them as subprocesses.

10. **Rules files are additive** — they add to CLAUDE.md, they don't replace it. A file matching `src/api/routes.py` gets BOTH the universal CLAUDE.md rules AND the api-conventions.md rules.
