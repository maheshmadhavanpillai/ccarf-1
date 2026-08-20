# Exercise 1: Multi-Tool Agent with Escalation Logic — Detailed Explanation

## Domains Reinforced
- **Domain 1:** Agentic Architecture & Orchestration
- **Domain 2:** Tool Design & MCP Integration
- **Domain 5:** Context Management & Reliability

---

## Step 1: MCP Tool Definitions (Lines 36–143)

### What it does
Defines 4 tools that Claude can choose from when processing user requests. These tools simulate a banking domain: `check_balance`, `get_transaction_history`, `transfer_funds`, and `update_contact_info`.

### How it works — Key Design Principles

| Principle | Example in the code |
|-----------|-------------------|
| **Positive framing** | "Use this when the user asks about how much money they have RIGHT NOW" |
| **Negative boundaries** | "Do NOT use this for historical data" |
| **Differentiation between similar tools** | `check_balance` vs `get_transaction_history` — both touch account data but one is point-in-time, the other is a range |
| **Side effect documentation** | `update_contact_info` notes "confirmation sent to OLD contact method" |
| **Threshold documentation** | `transfer_funds` warns about the $10K limit |

### Why this matters for the exam

Tool descriptions are the **only** way Claude decides which tool to call. If descriptions are ambiguous, Claude may call the wrong tool. This is why "negative boundaries" (do NOT use this for X) are critical — they prevent selection confusion between similar tools.

### The "Similar Tool" Problem

`check_balance` and `get_transaction_history` both access account data. Without explicit differentiation:
- A user asking "what happened in my account?" could trigger either tool
- A user asking "how much do I have?" might get transaction history instead of a balance

The solution: each tool explicitly states what it IS for and what it is NOT for, pointing to the correct alternative.

### Input Schema Design

Each tool uses JSON Schema to define its inputs:
- `required` fields enforce mandatory parameters
- `enum` constraints (like `["email", "phone", "address"]`) prevent invalid values
- `description` on each property guides the model on formatting (e.g., "format: ACC-XXXXX")

---

## Step 2: The Agentic Loop (Lines 265–325)

### What it does
Implements the core loop pattern that drives multi-step agent behavior. This is the "brain" of the agent — it decides when to keep working and when to stop.

### The Flow Diagram

```
User message
     │
     ▼
┌─────────────┐
│  Call Claude │◄─────────────────────────┐
│  (with tools)│                          │
└──────┬──────┘                           │
       │                                  │
       ▼                                  │
  stop_reason?                            │
       │                                  │
  ┌────┴────┐                             │
  │         │                             │
tool_use  end_turn                        │
  │         │                             │
  ▼         ▼                             │
Execute   Return text                     │
tools     to user                         │
  │                                       │
  ▼                                       │
Send results ─────────────────────────────┘
back as "user" message
```

### The stop_reason Control Signal

`stop_reason` is the critical field that drives the loop:

| stop_reason | Meaning | Agent action |
|-------------|---------|--------------|
| `"tool_use"` | Claude wants to call one or more tools | Execute the tools, send results back, loop again |
| `"end_turn"` | Claude has finished and composed its final answer | Extract text, return to user, exit loop |

### Message Threading

The conversation builds up like this across iterations:

```
messages = [
  {role: "user", content: "Check my balance on ACC-12345"},           # Original request
  {role: "assistant", content: [TextBlock, ToolUseBlock]},            # Claude's tool call
  {role: "user", content: [{type: "tool_result", tool_use_id, ...}]}, # Our tool results
  {role: "assistant", content: [TextBlock]},                          # Claude's final answer
]
```

**Critical detail:** Tool results are sent back as a `user` role message with `type: "tool_result"`. Each result must be paired with the `tool_use_id` from the assistant's request. This is mandatory API protocol.

### Safety: MAX_ITERATIONS

`MAX_ITERATIONS = 10` prevents infinite loops. Without this, a misbehaving model (or circular tool dependencies) could run forever. This is a **hard ceiling** — a reliability pattern for production systems.

### Parallel Tool Calls

Claude can request multiple tools in a single turn (multiple `tool_use` blocks in one response). The agent loop executes ALL of them before sending results back. This is more efficient than one tool per iteration — in Test 2, Claude calls `check_balance` and `get_transaction_history` simultaneously.

---

## Step 3: Structured Error Responses (Lines 146–172)

### What it does
Every tool error returns a structured object (not just a string) that the agent can programmatically reason about.

### The Error Schema

```json
{
  "error": true,
  "errorCategory": "transient | validation | permission",
  "isRetryable": true/false,
  "description": "Human-readable explanation"
}
```

### How the Agent Handles Each Error Type

| Category | isRetryable | Agent behavior | Example |
|----------|-------------|----------------|---------|
| `transient` | `true` | Automatically retries up to MAX_RETRIES times with backoff | Database timeout |
| `validation` | `false` | Reports the issue to the user, suggests corrections | Account not found |
| `permission` | `false` | Explains the escalation process and next steps | Transfer exceeds limit |

### The Retry Logic (Code Path)

```python
for attempt in range(MAX_RETRIES + 1):
    result = execute_tool(tool_name, tool_input)
    if result.get("error") and result.get("isRetryable"):
        if attempt < MAX_RETRIES:
            time.sleep(0.5)  # Backoff before retry
            continue
        else:
            break  # Give up after max retries
    break  # Success or non-retryable error
```

### Why Structured > Unstructured

Without structured errors, the agent would need to **interpret** error strings to decide whether to retry — this is unreliable and fragile. Consider:

- Unstructured: `"Error: connection timed out"` — model has to parse this text
- Structured: `{"errorCategory": "transient", "isRetryable": true}` — code can branch deterministically

The structured format makes retry logic **deterministic** (code-driven, not model-driven). The `description` field still provides human-readable context for the model to explain to the user.

---

## Step 4: Programmatic Hook / Escalation (Lines 175–203)

### What it does
Intercepts tool calls **before** execution to enforce hard business rules that cannot be bypassed.

### Architecture

```
Claude wants to call transfer_funds($15,000)
         │
         ▼
   escalation_hook()    ◄── Runs OUTSIDE the model
         │
    amount > $10,000?
         │
    ┌────┴────┐
   YES       NO
    │         │
    ▼         ▼
  BLOCK     Allow execution
  (return    (return None)
  error)     proceeds to execute_tool()
```

### Hard Guardrails vs. Soft Guardrails

This is a **key exam concept**:

| Approach | Type | Can be bypassed? | Example |
|----------|------|-----------------|---------|
| System prompt: "Don't transfer more than $10K" | Soft guardrail | YES — prompt injection could override | Model decides to comply (or not) |
| Programmatic hook that checks amount | Hard guardrail | NO — runs outside the model | Code enforces the rule |

The hook pattern is a **hard guardrail** because:
1. It runs in application code, not in the model's context
2. It cannot be influenced by conversation content
3. It executes BEFORE the tool, so blocked operations never reach the backend
4. It's deterministic and auditable (you can log every interception)

### The Escalation Response

When the hook blocks a call, it returns a structured error with `category: "permission"`. This tells Claude:
- The operation was denied (not failed)
- It should NOT retry
- It should explain the escalation process to the user
- It should provide the reference ID for follow-up

### Where Hooks Fit in Production

In a real MCP architecture, hooks can be:
- **Pre-execution hooks:** Check before a tool runs (our pattern)
- **Post-execution hooks:** Audit/log after a tool completes
- **Rate-limiting hooks:** Throttle tool calls per user/session
- **Authentication hooks:** Verify permissions before sensitive operations

---

## Step 5: Multi-Concern Handling (Test 2)

### What it does
Tests that Claude can decompose a message with multiple requests into individual tool calls and synthesize a unified response.

### The Observed Behavior

**User says:** "1) Check my balance, 2) Show transactions, 3) Update my email"

**Iteration 1:** Claude calls `check_balance` + `get_transaction_history` in parallel
- These are both read-only with no dependency between them
- Parallel execution is more efficient

**Iteration 2:** Claude calls `update_contact_info`
- This might logically depend on first confirming the account exists
- Claude sequences this after the reads

**Iteration 3:** Claude synthesizes all results into a unified response
- Addresses each concern in order
- Provides a cohesive summary, not three disconnected answers

### Why Multi-Concern Handling Matters

Real users don't ask one thing at a time. A production agent must:
1. **Decompose** — identify distinct sub-requests within a message
2. **Sequence** — determine dependencies (what must happen before what)
3. **Parallelize** — execute independent operations simultaneously
4. **Synthesize** — combine results into a coherent response

### The Transient Error During Multi-Concern

In Test 2, the `get_transaction_history` call hits a transient error on the first attempt. The agent:
1. Detects `isRetryable: true`
2. Waits briefly (backoff)
3. Retries successfully
4. Continues processing the remaining concerns

The user never sees this hiccup — it's handled transparently. This is the reliability benefit of structured error handling.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                    USER MESSAGE                          │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              AGENTIC LOOP (Step 2)                       │
│                                                         │
│  ┌───────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │  Claude   │───▶│ stop_reason  │───▶│  end_turn?  │──┼──▶ Final Response
│  │  API Call │    │    check     │    │  Return text│  │
│  └───────────┘    └──────┬───────┘    └─────────────┘  │
│                          │                              │
│                     tool_use                            │
│                          │                              │
│                          ▼                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │         HOOK LAYER (Step 4)                      │   │
│  │  escalation_hook() — hard business rules         │   │
│  │  Can BLOCK tool calls before execution           │   │
│  └──────────────────────┬──────────────────────────┘   │
│                          │                              │
│                    Allowed?                             │
│                    │     │                              │
│                   YES    NO ──▶ Return permission error │
│                    │                                    │
│                    ▼                                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │         TOOL EXECUTION + ERROR HANDLING (Step 3) │   │
│  │  execute_tool() — calls backend/MCP server       │   │
│  │  Retry loop for transient errors                 │   │
│  │  Structured error responses for all failures     │   │
│  └──────────────────────┬──────────────────────────┘   │
│                          │                              │
│                          ▼                              │
│              Send tool_results back to Claude           │
│              (loop continues)                           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Key Takeaways for the Exam

1. **Tool descriptions are routing logic** — they're how Claude picks the right tool. Invest in clear, explicit, boundary-aware descriptions.

2. **The agentic loop is driven by `stop_reason`** — `tool_use` means "keep going," `end_turn` means "I'm done." Always handle both.

3. **Structured errors enable deterministic handling** — don't make the model interpret error strings. Give it typed categories it can branch on.

4. **Hard guardrails (hooks) > soft guardrails (prompts)** — anything safety-critical should be enforced in code, not in the system prompt.

5. **Multi-concern decomposition is emergent** — Claude naturally breaks complex requests into steps. Your loop just needs to support multiple iterations.

6. **MAX_ITERATIONS is a reliability pattern** — always cap your loops. Unbounded agentic loops are a production risk.

7. **Parallel tool calls are an optimization** — Claude can request multiple tools per turn. Execute them all before responding.
