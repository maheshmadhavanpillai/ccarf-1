# Claude Certified Architect Foundations — Exam Prep Exercises

Practice exercises for the **Claude Certified Architect Foundations (CCARF)** exam, covering all 5 domains through hands-on implementation.

## Exercises

### [Exercise 1: Multi-Tool Agent with Escalation Logic](exercise_1/)

**Domains:** Agentic Architecture & Orchestration (D1), Tool Design & MCP Integration (D2), Context Management & Reliability (D5)

Builds a banking assistant agent that demonstrates the core agentic loop pattern.

| Concept | Implementation |
|---------|---------------|
| Tool definitions with clear boundaries | 4 MCP tools with explicit "use this for X, NOT for Y" descriptions |
| Agentic loop driven by `stop_reason` | `tool_use` → execute tools → loop; `end_turn` → return response |
| Structured error handling | Error categories (transient/validation/permission) with retry logic |
| Programmatic hooks (hard guardrails) | Pre-execution hook blocks transfers >$10K — cannot be prompt-injected |
| Multi-concern decomposition | Single message with 3 requests → sequential tool calls → unified response |

```bash
python exercise_1/exercise1_multi_tool_agent.py --demo
```

---

### [Exercise 2: Claude Code Team Development Workflow](exercise_2/)

**Domains:** Claude Code Configuration & Workflows (D3), Tool Design & MCP Integration (D2)

Configures a full Claude Code project structure demonstrating the configuration hierarchy.

| Concept | Implementation |
|---------|---------------|
| Project-level CLAUDE.md | Universal coding standards applied to all files/developers |
| Path-specific rules (`.claude/rules/`) | YAML frontmatter glob patterns: `src/api/**/*`, `**/*.test.*`, `src/db/**/*` |
| Custom skills (`.claude/skills/`) | `/run-migration` with `context: fork` and `allowed-tools` restrictions |
| MCP server configuration | `.mcp.json` with `${POSTGRES_URL}` environment variable expansion |
| Plan mode vs direct execution | When to plan (multi-file, multi-approach) vs execute directly (simple fix) |

**Key files:**
- `exercise_2/CLAUDE.md` — Universal project standards
- `exercise_2/rules/` — Path-specific rules with glob patterns
- `exercise_2/skills/run-migration.md` — Isolated skill with tool restrictions
- `exercise_2/.mcp.json` — MCP server config with env var expansion

---

### [Exercise 3: Structured Data Extraction Pipeline](exercise_3/)

**Domains:** Prompt Engineering & Structured Output (D4), Context Management & Reliability (D5)

Builds a document extraction pipeline with validation, retries, batch processing, and human review routing.

| Concept | Implementation |
|---------|---------------|
| JSON schema with nullable fields | `["string", "null"]` type unions prevent hallucination |
| Enum + "other" + detail pattern | Semi-open categories with escape hatch |
| `tool_choice` for forced structured output | `{"type": "tool", "name": "..."}` guarantees JSON conformance |
| Validation-retry loop | Classify errors (resolvable vs unresolvable), retry with specific feedback |
| Few-shot examples | 3 examples covering well-structured, minimal, and narrative documents |
| Message Batches API | Async batch of 100 docs, custom_id tracking, chunking oversized documents |
| Human review routing | Per-field confidence thresholds, route low-confidence to humans |
| Accuracy tracking | Aggregate confidence by document type to find systematic weaknesses |

```bash
python exercise_3/extraction_pipeline.py --demo
```

---

### [Exercise 4: Multi-Agent Research Pipeline](exercise_4/)

**Domains:** Agentic Architecture & Orchestration (D1), Tool Design & MCP Integration (D2), Context Management & Reliability (D5)

Orchestrates a coordinator agent that delegates to subagents, handles failures gracefully, and synthesizes findings with conflict detection.

| Concept | Implementation |
|---------|---------------|
| Coordinator → subagent delegation | Explicit context passing (no automatic inheritance) |
| Parallel subagent execution | Multiple tool_use blocks in one response → concurrent execution |
| Structured findings with provenance | Every claim has finding_id, source, date, confidence |
| Error propagation | Timeout returns partial results + coverage gap annotation |
| Graceful degradation | Use partial results, annotate what's missing |
| Conflict detection in synthesis | Sources disagree (35% vs 50%) → preserve both with attribution |
| Established vs contested findings | Report clearly separates high-confidence from disputed claims |

```bash
python exercise_4/research_pipeline.py --demo
```

---

### [Exercise 5: Build an Agent with the Claude Agent SDK](exercise_5/)

**Domains:** Agentic Architecture & Orchestration (D1), Tool Design & MCP Integration (D2), Context Management & Reliability (D5)

Implements a complete agentic loop demonstrating tool calling, error handling, session management, and subagent spawning patterns.

| Concept | Implementation |
|---------|---------------|
| Agentic loop (stop_reason driven) | `tool_use` → execute tools → loop; `end_turn` → return |
| Tool registration (decorator pattern) | `@register_tool` mimics `@beta_tool` from Tool Runner |
| Error classification | Transient/validation/context_overflow with retry guidance |
| Session management | Token tracking, 80% threshold, automatic compaction |
| Subagent spawning | Coordinator decomposes → parallel subagents with explicit context |
| Tool Runner hooks | `on_tool_call` (approval gate), `on_tool_result` (redaction) |

```bash
python exercise_5/exercise5_agent_sdk.py --demo
```

---

### [Exercise 6: Configure Claude Code for a Real Project](exercise_6/)

**Domains:** Claude Code Configuration & Workflows (D3), Tool Design & MCP Integration (D2)

Configures a complete Claude Code project for a SaaS analytics platform, demonstrating the full configuration hierarchy with real-world patterns.

| Concept | Implementation |
|---------|---------------|
| CLAUDE.md (universal standards) | Python/TS conventions, security rules, plan mode guidance |
| Path-specific rules (4 files) | API layer, workers, testing, frontend — each with glob patterns |
| Custom skills (3 skills) | `/run-pipeline`, `/deploy-preview`, `/generate-migration` |
| `context: fork` isolation | Skills run in separate context windows |
| `allowed-tools` restriction | `/deploy-preview` has NO Write access (hard guardrail) |
| MCP server integration (3 servers) | PostgreSQL, GitHub, Sentry with `${ENV_VAR}` expansion |

**Key files:**
- `exercise_6/CLAUDE.md` — Universal project standards
- `exercise_6/.claude/rules/` — 4 path-specific rule files
- `exercise_6/.claude/skills/` — 3 skills with varying tool restrictions
- `exercise_6/.mcp.json` — 3 MCP servers with env var expansion

---

## Domain Coverage Matrix

| Domain | Ex 1 | Ex 2 | Ex 3 | Ex 4 | Ex 5 | Ex 6 |
|--------|:----:|:----:|:----:|:----:|:----:|:----:|
| D1: Agentic Architecture & Orchestration | ✓ | | | ✓ | ✓ | |
| D2: Tool Design & MCP Integration | ✓ | ✓ | | ✓ | ✓ | ✓ |
| D3: Claude Code Configuration & Workflows | | ✓ | | | | ✓ |
| D4: Prompt Engineering & Structured Output | | | ✓ | | | |
| D5: Context Management & Reliability | ✓ | | ✓ | ✓ | ✓ | |

## Running the Exercises

All exercises have a `--demo` mode that simulates the pipeline without needing an API key:

```bash
python exercise_1/exercise1_multi_tool_agent.py --demo
python exercise_3/extraction_pipeline.py --demo
python exercise_4/research_pipeline.py --demo
python exercise_5/exercise5_agent_sdk.py --demo
```

Exercise 6 is a configuration reference (no executable script) — study the file structure, rules, skills, and MCP config.

For live mode (calls the Claude API):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python exercise_1/exercise1_multi_tool_agent.py
python exercise_3/extraction_pipeline.py
python exercise_4/research_pipeline.py
python exercise_5/exercise5_agent_sdk.py
```

Exercise 2 is a configuration reference (no executable script) — study the file structure and rules.

## Key Patterns Across All Exercises

| Pattern | Where it appears |
|---------|-----------------|
| **Agentic loop** (stop_reason check) | Ex 1, Ex 4, Ex 5 |
| **Structured errors** (category + retryable) | Ex 1, Ex 3, Ex 4, Ex 5 |
| **Hard guardrails** (programmatic hooks) | Ex 1 (escalation), Ex 2 (allowed-tools), Ex 5 (Tool Runner hooks) |
| **Parallel execution** | Ex 4 (subagents), Ex 3 (batch API), Ex 5 (subagent spawning) |
| **Provenance tracking** | Ex 3 (source attribution), Ex 4 (finding_ids) |
| **Graceful degradation** | Ex 3 (retry loop), Ex 4 (partial results), Ex 5 (error classification) |
| **Context isolation** | Ex 2 (fork context), Ex 4 (no inheritance), Ex 5 (subagent sessions) |
| **Conflict handling** | Ex 4 (contested findings), Ex 3 (validation errors) |
| **Session management** | Ex 5 (token tracking + compaction) |
| **Tool Runner pattern** | Ex 5 (decorator registration + SDK-managed loop) |
