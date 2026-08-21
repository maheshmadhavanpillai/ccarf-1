# Exercise 5: Build an Agent with the Claude Agent SDK — Detailed Explanation

## Domains Reinforced
- **Domain 1:** Agentic Architecture & Orchestration
- **Domain 2:** Tool Design & MCP Integration
- **Domain 5:** Context Management & Reliability

---

## Overview: Four Approaches to Building Agents

Before diving into the implementation, understand the four ways to build Claude agents:

| # | Approach | You Write | Loop Owner | Tools Available |
|---|----------|-----------|------------|-----------------|
| 1 | **Manual Loop** | The `while stop_reason == "tool_use"` loop | You | Your tools only |
| 2 | **Tool Runner** (`client.beta.messages.tool_runner` + `@beta_tool`) | Tool functions + hooks | SDK | Your tools only |
| 3 | **Managed Agents** (REST API) | Agent config + tool results | Anthropic | Sandbox + MCP + yours |
| 4 | **Claude Agent SDK** (`claude-agent-sdk`) | A prompt + options | SDK (Claude Code harness) | Built-in + MCP + subagents |

This exercise implements patterns from approaches **1 and 2** (manual loop + tool runner), which are what the CCARF exam tests.

### Key Distinction

- **Tool Runner** = SDK helper that automates the loop for **your** custom tools (part of `anthropic` package)
- **Claude Agent SDK** = Claude Code packaged as a library with **built-in** tools (separate `claude-agent-sdk` package)
- **Managed Agents** = Anthropic hosts the loop AND the sandbox (no loop code on your side)

---

## Step 1: Tool Registration (Decorator Pattern)

### What it does
Tools are registered using a decorator pattern that mirrors the `@beta_tool` decorator in the SDK's Tool Runner. Each tool has a name, description, JSON schema for parameters, and a handler function.

### The Pattern

```python
TOOL_REGISTRY: dict[str, dict] = {}

def register_tool(name, description, parameters):
    def decorator(func):
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "input_schema": {"type": "object", "properties": parameters, ...},
            "handler": func,
        }
        return func
    return decorator

@register_tool(name="search_knowledge_base", ...)
def search_knowledge_base(query: str, max_results: int) -> dict:
    ...
```

### Why This Pattern

| Design Choice | Reason |
|--------------|--------|
| Decorator registration | Tools are defined once, schema + handler stay together |
| Separate registry dict | Loop can iterate tools without importing each function |
| JSON Schema `input_schema` | Matches Claude API's tool definition format exactly |
| Handler returns dict | Structured result that the model can parse |

### Tool Design Principles

1. **Clear boundary descriptions** — "Use for X, NOT for Y"
2. **Typed parameters** — JSON Schema validates inputs before execution
3. **Structured returns** — Always return a dict with consistent shape
4. **Error in result** — Failed tools return `{"error": ..., "error_type": ...}` not exceptions

### Exam Insight

The `@beta_tool` decorator in the real SDK does exactly this — registers a function as a tool with its schema. The Tool Runner then:
1. Sends tool definitions to Claude
2. Receives tool_use blocks
3. Calls your decorated functions
4. Sends results back
5. Loops until end_turn

---

## Step 2: The Agentic Loop

### What it does
The core loop sends messages to Claude, checks the `stop_reason`, executes any tool calls, and loops until the model is done.

### The Loop Logic

```
┌─────────────────────────────────────────────────────────┐
│                  AGENTIC LOOP                             │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  while iteration < max_iterations:                        │
│    │                                                      │
│    ├── [Context check] Need compaction? → compact()       │
│    │                                                      │
│    ├── Send messages + tools to Claude API                │
│    │                                                      │
│    ├── Receive response                                   │
│    │     │                                                │
│    │     ├── stop_reason == "end_turn"                    │
│    │     │     → Extract text blocks → RETURN response    │
│    │     │                                                │
│    │     ├── stop_reason == "tool_use"                    │
│    │     │     → Execute each tool_use block              │
│    │     │     → Add tool_results to messages             │
│    │     │     → CONTINUE loop                            │
│    │     │                                                │
│    │     └── unexpected stop_reason                       │
│    │           → RETURN with error status                 │
│    │                                                      │
│    └── [Safety] Max iterations reached → RETURN           │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### Critical: stop_reason Drives the Loop

| stop_reason | Meaning | Action |
|-------------|---------|--------|
| `"tool_use"` | Model wants to call tools | Execute tools, feed results back, loop |
| `"end_turn"` | Model is done | Extract final text, return to user |
| `"max_tokens"` | Response was cut off | Could continue or return partial |

### Why max_iterations Matters

Without a safety bound, a confused model could loop forever calling tools that don't resolve its query. The `max_iterations` parameter (typically 10-25) ensures termination.

### Message History Accumulation

Each iteration adds to the message history:
```
Turn 1: user message
Turn 2: assistant (tool_use) → user (tool_result)
Turn 3: assistant (tool_use) → user (tool_result)
Turn 4: assistant (end_turn with final text)
```

The model sees ALL previous turns, which is why context management matters.

### Exam Insight

The agentic loop is THE fundamental pattern. Every agent — manual, Tool Runner, Managed, or SDK — implements this loop internally. Understanding it means understanding agents.

---

## Step 3: Error Handling with Classification

### What it does
Errors are classified into typed categories, each with specific retry guidance. This replaces generic try/except with structured, actionable error handling.

### Error Categories

| Category | Examples | Retryable? | Action |
|----------|----------|------------|--------|
| `transient` | Rate limit (429), overloaded (529) | Yes | Exponential backoff |
| `context_overflow` | Too many tokens | Yes | Compact session, then retry |
| `validation` | Invalid schema, bad parameters | No | Return error to model |
| `tool_failure` | Tool crashed, timeout | Maybe | Retry up to 3 times |

### Exponential Backoff Strategy

```python
retry_after = min(2 ** attempt, 30)  # 2s, 4s, 8s, 16s, 30s cap
```

For overloaded errors, multiply by 2:
```python
retry_after = min(2 ** attempt * 2, 60)  # 4s, 8s, 16s, 32s, 60s cap
```

### Context Overflow Recovery

When the context window is exceeded:
1. Classify as `context_overflow` (not a fatal error)
2. Set action to `compact_and_retry`
3. The loop calls `session.compact()` to summarize old messages
4. Retry with the reduced context

### Why Classification Matters

| Without Classification | With Classification |
|-----------------------|---------------------|
| `except Exception: retry()` | Retry only retryable errors |
| Same backoff for everything | Backoff scaled to error severity |
| No recovery for context issues | Context compaction as recovery strategy |
| Infinite retries possible | Bounded retries with clear escalation |

### Exam Insight

Error classification is how production agents stay reliable:
- **Transient errors** → wait and retry (the problem will resolve)
- **Validation errors** → don't retry (same input = same error)
- **Context overflow** → compact and retry (reduce the input)
- **Tool failures** → limited retries, then degrade gracefully

---

## Step 4: Session Management

### What it does
The `Session` class tracks conversation state, estimates token usage, and compacts old messages when approaching the context window limit.

### Session State

```python
@dataclass
class Session:
    session_id: str          # Unique identifier
    messages: list[dict]     # Full conversation history
    metadata: dict           # Arbitrary session metadata
    max_context_tokens: int  # Context window size (200K for Claude)
    estimated_tokens_used: int  # Running estimate
    turn_count: int          # Number of user turns
```

### Token Estimation

Exact token counting requires the tokenizer. For session management, a rough estimate works:
```python
estimated_tokens = len(content) // 4  # ~4 chars per token
```

### Context Window Awareness

```
┌─────────────────────────────────────────────────────────┐
│ CONTEXT WINDOW (200K tokens)                             │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  [██████████████████░░░░░░░░░░░░░░░░░░░░]               │
│   ▲                  ▲                    ▲              │
│   │                  │                    │              │
│   Used (40%)         80% threshold        Max            │
│                      ↓                                    │
│              TRIGGER COMPACTION                           │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

At 80% usage, the session compacts older messages into a summary.

### Compaction Strategy

1. Keep the **last 4 messages** (current context is most important)
2. Summarize everything older into a single "summary" message
3. Replace the message history with: `[summary] + [last 4 messages]`
4. Recalculate token estimate

### Why 80% Threshold

- Too early (50%) = unnecessary information loss
- Too late (95%) = risk of exceeding the limit before next API call
- 80% = safe margin that preserves recent context

### Multi-Turn Conversation Flow

```
Turn 1: "What's your refund policy?"         → tokens: 1200
Turn 2: "Can I return after 30 days?"        → tokens: 2400
Turn 3: "What about order ORD-12345?"        → tokens: 3800
Turn 4: [COMPACT: summarize turns 1-2]       → tokens: 2100
Turn 5: "And shipping for the replacement?"  → tokens: 2900
```

### Exam Insight

Session management is a Domain 5 (Context Management & Reliability) concern:
- Track token usage to prevent overflow
- Compact proactively (before errors, not after)
- Preserve recent context over old context
- The summary preserves WHAT was discussed, not the exact wording

---

## Step 5: Subagent Spawning (Coordinator Pattern)

### What it does
A coordinator agent decomposes a complex query into subtasks, spawns specialized subagents with explicit context, executes them in parallel, and synthesizes the results.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     COORDINATOR                               │
│                                                               │
│  1. Analyze query → identify needed capabilities             │
│  2. Decompose into self-contained subtasks                   │
│  3. Spawn subagents (each with OWN session)                  │
│  4. Execute in parallel (ThreadPoolExecutor)                 │
│  5. Collect results → synthesize unified response            │
│                                                               │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ SUBAGENT A   │  │ SUBAGENT B   │  │ SUBAGENT C   │
│              │  │              │  │              │
│ Own session  │  │ Own session  │  │ Own session  │
│ Own context  │  │ Own context  │  │ Own context  │
│ Explicit     │  │ Explicit     │  │ Explicit     │
│ prompt only  │  │ prompt only  │  │ prompt only  │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Explicit Context Passing (Critical Concept)

Each subagent receives ONLY what the coordinator puts in its prompt:

```python
SubagentTask(
    prompt=f"Look up order {oid} for customer {customer_id}. "
           f"Return the full order details including status, items, "
           f"and tracking information.",
    context={"order_id": oid, "customer_id": customer_id},
)
```

The subagent does NOT see:
- The coordinator's conversation history
- Other subagents' results
- The original user message (unless explicitly included)

### Why No Context Inheritance

| With Inheritance | Without (Explicit) |
|-----------------|-------------------|
| Subagent confused by irrelevant info | Subagent sees only what it needs |
| Context window waste | Minimal, focused context |
| Privacy leakage between customers | Isolation by default |
| Hard to test (depends on parent state) | Easy to test (self-contained input) |

### Parallel Execution

```python
with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
    futures = {executor.submit(spawn_subagent, task): task for task in tasks}
    for future in as_completed(futures):
        results.append(future.result())
```

Wall-clock time = max(individual subagent times), not sum.

### Query Decomposition

The coordinator decides which subagents to spawn based on the query:

| Query Contains | Subagent Spawned |
|---------------|------------------|
| Order ID (ORD-XXXXX) | `order_lookup` |
| "refund", "return" | `policy_lookup` |
| "stock", "available" | `inventory_check` |
| "issue", "problem" | `ticket_handler` |
| None of the above | `general_search` |

### Synthesis

After all subagents complete:
1. Separate successful results from failures
2. Combine successful response parts
3. Annotate any coverage gaps from failed subagents
4. Return unified response with status

### Exam Insight

The coordinator pattern is the exam's preferred multi-agent architecture:
1. **Explicit context** — coordinator passes everything subagent needs
2. **Own session** — each subagent starts fresh (no inheritance)
3. **Parallel execution** — multiple tool_use blocks = concurrent spawning
4. **Graceful degradation** — partial results + gap annotation if some fail

---

## Step 6: Tool Runner Pattern (Hooks)

### What it does
The Tool Runner automates the agentic loop while providing **hooks** — callback functions that execute at specific points in the loop. This gives you control without writing the loop yourself.

### Hook Points

```
┌─────────────────────────────────────────────────────────┐
│                   TOOL RUNNER LOOP                        │
│                                                           │
│  API Response received                                    │
│       │                                                   │
│       ▼                                                   │
│  ┌─────────────────────────┐                             │
│  │ TOOL CALL DETECTED      │                             │
│  └────────────┬────────────┘                             │
│               │                                           │
│               ▼                                           │
│  ┌─────────────────────────┐                             │
│  │ on_tool_call HOOK       │  ← Approval gate            │
│  │ (pre-execution)         │    Returns True/False        │
│  └────────────┬────────────┘                             │
│               │                                           │
│          approved?                                        │
│          /       \                                        │
│        Yes        No → return error to model              │
│         │                                                 │
│         ▼                                                 │
│  ┌─────────────────────────┐                             │
│  │ EXECUTE TOOL            │                             │
│  └────────────┬────────────┘                             │
│               │                                           │
│               ▼                                           │
│  ┌─────────────────────────┐                             │
│  │ on_tool_result HOOK     │  ← Result modification      │
│  │ (post-execution)        │    Redact, cache, transform  │
│  └────────────┬────────────┘                             │
│               │                                           │
│               ▼                                           │
│  Feed result back to model → next iteration               │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### Hook Types and Use Cases

| Hook | When It Runs | Use Cases |
|------|-------------|-----------|
| `on_tool_call` | Before tool execution | Approval gates, rate limiting, logging, blocking dangerous ops |
| `on_tool_result` | After tool execution | Redact PII, add cache_control, transform results, log outputs |
| `on_error` | When tool throws | Classify errors, decide retry/abort, alert monitoring |

### Approval Gate Example

```python
def approval_hook(tool_call: dict) -> bool:
    # Block low-priority ticket creation (waste of human time)
    if tool_call["name"] == "create_ticket":
        if tool_call["input"].get("priority") == "low":
            return False  # Blocked!
    return True  # Approved
```

### Result Modification Example

```python
def result_hook(tool_call: dict, result: dict) -> dict:
    # Redact tracking numbers before they enter the conversation
    if tool_call["name"] == "lookup_order":
        order = result["result"].get("order", {})
        if order.get("tracking"):
            order["tracking"] = order["tracking"][:4] + "***"
    return result  # Modified result goes back to model
```

### Hooks vs Programmatic Guards (Exercise 1)

| Feature | Hooks (Tool Runner) | Programmatic Guards (Exercise 1) |
|---------|--------------------|---------------------------------|
| Where they run | Inside SDK loop | Before/after your manual loop |
| Can be prompt-injected? | No (code, not prompt) | No (code, not prompt) |
| Granularity | Per-tool-call | Per-operation |
| Who manages the loop? | SDK | You |

Both are **hard guardrails** — they're code that runs regardless of what the model says. The difference is who owns the loop.

### Exam Insight

The Tool Runner's hooks are how you maintain control while letting the SDK manage the loop:
- `on_tool_call` = **approval gate** (can the model do this?)
- `on_tool_result` = **result filter** (what does the model see back?)
- Neither can be bypassed by prompt injection (they're code, not instructions)

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                    EXERCISE 5: COMPLETE AGENT ARCHITECTURE            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │ TOOL REGISTRY (decorator-based)                                │   │
│  │ • search_knowledge_base    • lookup_order                      │   │
│  │ • create_ticket            • check_inventory                   │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                          │                                            │
│                          ▼                                            │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │ AGENTIC LOOP (stop_reason driven)                              │   │
│  │                                                                 │   │
│  │  send → check stop_reason → tool_use? execute : end_turn       │   │
│  │                                                                 │   │
│  │  With: • Error classification (transient/validation/overflow)  │   │
│  │        • Exponential backoff                                    │   │
│  │        • Context overflow recovery (compact + retry)            │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                          │                                            │
│                          ▼                                            │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │ SESSION MANAGEMENT                                             │   │
│  │                                                                 │   │
│  │  • Token tracking (estimated)                                  │   │
│  │  • 80% threshold → trigger compaction                          │   │
│  │  • Keep last 4 messages + summarize the rest                   │   │
│  │  • Multi-turn state preservation                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                          │                                            │
│                          ▼                                            │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │ COORDINATOR + SUBAGENTS                                        │   │
│  │                                                                 │   │
│  │  Coordinator:                                                   │   │
│  │  • Decompose query into subtasks                               │   │
│  │  • Pass EXPLICIT context (no inheritance)                      │   │
│  │  • Spawn subagents in PARALLEL                                 │   │
│  │  • Synthesize results + annotate gaps                          │   │
│  │                                                                 │   │
│  │  Subagents:                                                     │   │
│  │  • Own session (isolated)                                      │   │
│  │  • Self-contained prompt                                       │   │
│  │  • Return structured results                                   │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                          │                                            │
│                          ▼                                            │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │ TOOL RUNNER (SDK-managed loop + hooks)                         │   │
│  │                                                                 │   │
│  │  • on_tool_call: approval gate (block dangerous operations)    │   │
│  │  • on_tool_result: result filter (redact, transform, cache)    │   │
│  │  • Cannot be prompt-injected (hard guardrails)                 │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways for the Exam

1. **The agentic loop is driven by `stop_reason`** — `"tool_use"` means keep going, `"end_turn"` means done. This is the ONE pattern that all agent approaches share.

2. **Tool Runner ≠ Claude Agent SDK** — Tool Runner is an SDK helper that automates the loop for YOUR tools. The Agent SDK is Claude Code as a library with built-in tools. Don't confuse them on the exam.

3. **Hooks are hard guardrails** — `on_tool_call` and `on_tool_result` hooks are code that cannot be bypassed by prompt injection. They provide approval gates and result filtering.

4. **Sessions need proactive compaction** — Don't wait for context overflow errors. Track token usage and compact at 80% to maintain headroom for the next API call.

5. **Subagents get explicit context only** — The coordinator must include ALL needed information in the subagent's prompt. Subagents do NOT inherit the parent's conversation history.

6. **Error classification enables smart retries** — Rate limits get exponential backoff, context overflow gets compaction, validation errors are not retried. Generic `except: retry()` is wrong.

7. **Parallel execution = multiple tool_use blocks** — When the model emits multiple tool calls in one response, execute them concurrently. Speedup = sequential_time / parallel_time.

8. **Synthesis must handle partial results** — When some subagents fail, use their partial results and annotate coverage gaps. Never discard work that was partially completed.

9. **The four approaches differ in who owns the loop and deployment**:
   - Manual: you own everything
   - Tool Runner: SDK owns the loop, you host
   - Managed Agents: Anthropic owns loop + deployment
   - Agent SDK: SDK owns the loop (with built-in tools), you host

10. **max_iterations is a safety bound** — Without it, a confused model could loop forever. Typical values: 10 for simple agents, 25 for complex research tasks.
