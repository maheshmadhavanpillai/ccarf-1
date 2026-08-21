# Exercise 4: Multi-Agent Research Pipeline — Detailed Explanation

## Domains Reinforced
- **Domain 1:** Agentic Architecture & Orchestration
- **Domain 2:** Tool Design & MCP Integration
- **Domain 5:** Context Management & Reliability

---

## Step 1: Coordinator Agent with Subagent Delegation

### What it does
A **coordinator agent** orchestrates research by delegating specific queries to specialized **subagents** (web search and document analysis). Each subagent receives its full context directly in its prompt — no automatic context inheritance.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  COORDINATOR AGENT                        │
│  - Analyzes research topic                               │
│  - Decides which subagents to invoke                     │
│  - Passes FULL context in each delegation                │
│  - Has "Task" in allowedTools                            │
└────────────┬──────────────────────────┬─────────────────┘
             │                          │
             ▼                          ▼
┌────────────────────┐    ┌────────────────────────────┐
│  WEB SEARCH        │    │  DOCUMENT ANALYSIS          │
│  SUBAGENT          │    │  SUBAGENT                   │
│                    │    │                              │
│  Receives:         │    │  Receives:                  │
│  - Self-contained  │    │  - Self-contained query     │
│    query           │    │  - Document list            │
│  - Focus areas     │    │  - Analysis type            │
│  - Max sources     │    │                              │
│                    │    │  Does NOT see:              │
│  Does NOT see:     │    │  - Coordinator's history    │
│  - Coordinator's   │    │  - Other subagent results   │
│    conversation    │    │  - User's original request  │
│  - Other results   │    │                              │
└────────────────────┘    └────────────────────────────┘
```

### Why Explicit Context Passing (Not Automatic Inheritance)

| Approach | Behavior | Problem |
|----------|----------|---------|
| **Automatic inheritance** | Subagent sees full coordinator history | Context window waste, confusion from irrelevant info, privacy leakage |
| **Explicit passing** (our approach) | Subagent ONLY sees what coordinator provides | Clean, focused, predictable, testable |

The coordinator must make each delegation **self-contained**:

```python
# BAD: Assumes subagent knows the research topic
"Find more sources"

# GOOD: Self-contained query with full context
"Find recent studies (2022-2024) on enterprise AI adoption rates,
 including market size projections and growth forecasts. Focus on
 peer-reviewed sources and major consulting firm surveys."
```

### Tool Design for Delegation

```python
{
    "name": "delegate_web_search",
    "input_schema": {
        "properties": {
            "query": {
                "description": "Specific research question. Must be self-contained."
            },
            "focus_areas": {
                "description": "Specific aspects to focus on"
            },
            "max_sources": {
                "description": "Maximum sources to return"
            }
        }
    }
}
```

The tool descriptions explicitly state "the subagent does NOT inherit the coordinator's conversation history" — this guides the model to write complete queries.

### Exam Insight

**allowedTools: ["Task"]** — The coordinator must have the Task tool available to spawn subagents. Without it, the coordinator cannot delegate. This is an explicit permission that controls what agents can do.

---

## Step 2: Parallel Subagent Execution

### What it does
The coordinator emits **multiple Task tool calls in a single response**. We execute all delegations simultaneously and measure the latency improvement.

### How Parallel Execution Works

```
SEQUENTIAL (one at a time):
─────────────────────────────────────────────────
│ Web Search (200ms) │ Doc Analysis (150ms) │
─────────────────────────────────────────────────
Total: 350ms

PARALLEL (simultaneous):
─────────────────────────────────
│ Web Search (200ms)            │
│ Doc Analysis (150ms) │        │
─────────────────────────────────
Total: 200ms (limited by slowest)
```

### The Coordinator's Response Pattern

In a single response, the coordinator emits multiple tool calls:

```json
{
  "content": [
    {"type": "text", "text": "I'll research this topic from multiple angles..."},
    {"type": "tool_use", "name": "delegate_web_search", "input": {...}},
    {"type": "tool_use", "name": "delegate_document_analysis", "input": {...}}
  ]
}
```

Both tool_use blocks in ONE response = parallel execution signal.

### Implementation

```python
def execute_subagents_parallel(tasks):
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(_dispatch_task, task): task for task in tasks}
        for future in as_completed(futures):
            results.append(future.result())
    return results
```

### Measured Results (Demo)

```
Parallel time:    205ms
Sequential time:  356ms
Speedup:          1.74x
Time saved:       151ms
```

### Exam Insight

Parallel execution is triggered when the model returns multiple tool_use blocks in one response. The orchestration layer must:
1. Detect multiple tool calls in one response
2. Execute them concurrently (threads, asyncio, or actual parallel API calls)
3. Collect all results before feeding back to the model
4. The speedup = sequential_time / parallel_time (bounded by slowest subagent)

---

## Step 3: Structured Output with Provenance

### What it does
Every finding from a subagent separates **content** (the claim, the evidence) from **metadata** (where it came from, when, how confident). This enables provenance tracking through the entire pipeline.

### The Finding Schema

```python
@dataclass
class Finding:
    # CONTENT (what was found)
    claim: str                    # The factual claim
    evidence_excerpt: str         # Direct quote supporting it

    # METADATA (provenance)
    source_url: str              # Where it came from
    source_name: str             # Human-readable source
    publication_date: str | None  # When published

    # QUALITY
    confidence: float            # How confident (0-1)
    finding_id: str              # Unique ID for tracking
```

### Why Separate Content from Metadata

| Without separation | With separation |
|-------------------|----------------|
| "AI adoption is 35% (McKinsey 2023)" | `claim: "AI adoption is 35%"` + `source: "McKinsey"` + `date: "2023"` |
| Can't programmatically trace sources | Can filter by source, date, confidence |
| Synthesis loses attribution | Synthesis preserves exact provenance |
| Can't detect conflicts | Can compare claims across sources |

### Finding IDs Enable Tracing

Every finding gets a unique ID (e.g., `F-8b846111`). When the synthesis references a claim, it uses the finding_id:

```json
{
  "claim": "Global AI market projected to reach $1.81T by 2030",
  "supporting_finding_ids": ["F-8b846111"],
  "conflicting_finding_ids": []
}
```

This means: "This claim comes from finding F-8b846111, which is from Grand View Research (2024-01)." Full traceability from synthesis back to raw source.

### Exam Insight

Provenance tracking is a **reliability requirement** for production research systems. Without it:
- Users can't verify claims
- Conflicts can't be detected programmatically
- Coverage gaps aren't visible
- The synthesis appears authoritative when it may be based on a single unreliable source

---

## Step 4: Error Propagation with Partial Results

### What it does
When a subagent fails (timeout, rate limit, source unavailable), it returns **structured error context** — not just an error message, but exactly what was attempted, what was gathered before failure, and what information is now missing.

### The Error Schema

```python
@dataclass
class SubagentError:
    failure_type: str        # "timeout", "rate_limit", "source_unavailable"
    attempted_query: str     # What was being researched
    partial_results: list    # Findings gathered BEFORE failure
    error_message: str       # Human-readable description
    is_retryable: bool       # Can the coordinator try again?
    coverage_gap: str        # What's now missing from the report
```

### The Error Flow

```
Subagent starts research
    │
    ├── Finds 1 source (partial result)
    │
    ├── ⚡ TIMEOUT after 30 seconds
    │
    ▼
Returns SubagentResult with:
  status: "partial"
  findings: [1 finding gathered before timeout]
  error_context: {
    failure_type: "timeout",
    partial_results: [the 1 finding],
    coverage_gap: "Academic sources missing",
    is_retryable: true
  }
```

### Coordinator's Response Options

| Error Property | Coordinator Action |
|---------------|-------------------|
| `is_retryable: true` | CAN retry (but doesn't have to) |
| `is_retryable: false` | Must proceed without this data |
| `partial_results: [...]` | Include in synthesis with caveats |
| `coverage_gap: "..."` | Annotate final report |

### What the Coordinator Does

1. **Accepts partial results** — doesn't discard work already done
2. **Records the coverage gap** — user knows what's missing
3. **Annotates the final output** — "Note: academic sources could not be retrieved"
4. **Makes a retry decision** — in this case, proceeds without retry

### Why This Beats Simple Error Handling

| Simple approach | Our approach |
|----------------|--------------|
| Subagent fails → entire pipeline fails | Subagent fails → graceful degradation |
| Error: "timeout" (string) | Error: structured context with partial results |
| Coordinator retries blindly | Coordinator makes informed retry/proceed decision |
| User gets no report | User gets partial report with clear gap annotations |

### Exam Insight

Error propagation in multi-agent systems must be:
1. **Structured** — not just strings; typed error categories
2. **Informative** — include what was attempted and what was gathered
3. **Actionable** — tell the coordinator whether to retry or proceed
4. **Transparent** — coverage gaps propagate to the final user-facing output

---

## Step 5: Conflict Detection and Synthesis

### What it does
When multiple sources report different values for the same metric, the synthesis preserves **BOTH** values with full attribution rather than silently picking one. The final report separates "established" findings from "contested" ones.

### The Conflict Example

```
Source A (McKinsey, 2023-08):
  "AI adoption rate among enterprises reached 35% in 2023"

Source B (Internal Survey, 2023-12):
  "AI adoption rate among enterprises reached 50% in 2023"

Source C (Enterprise Tech Survey, 2024-09):
  "Enterprise AI adoption is 55% in large companies"
```

Three credible sources, three different numbers. What should the synthesis do?

### WRONG: Pick One Silently

```
"Enterprise AI adoption reached 35% in 2023."
```

This discards information and appears authoritative when it's actually contested.

### RIGHT: Preserve Both with Attribution

```json
{
  "status": "contested",
  "claim": "AI adoption rate: McKinsey vs Internal Survey",
  "resolution_note": "McKinsey (2023-08) reports 35% while Internal Survey (2023-12) reports 50%. Difference may be due to survey methodology, sample size, or definition of 'adoption'."
}
```

### The Synthesis Report Structure

```
┌─────────────────────────────────────────┐
│ SYNTHESIS REPORT                         │
├─────────────────────────────────────────┤
│                                          │
│ ESTABLISHED FINDINGS                     │
│ (High agreement across sources)          │
│ • Market size: $1.81T by 2030 [F-xxx]   │
│ • Healthcare AI: $45.2B by 2026 [F-yyy] │
│                                          │
│ CONTESTED FINDINGS                       │
│ (Sources disagree)                       │
│ • Adoption rate: 35% vs 50% vs 55%      │
│   Source A says X, Source B says Y       │
│   Possible reasons for discrepancy...    │
│                                          │
│ COVERAGE GAPS                            │
│ (What couldn't be determined)            │
│ ⚠ Academic sources unavailable           │
│ ⚠ Peer-reviewed validation missing       │
│                                          │
│ SOURCES                                  │
│ • Grand View Research (2024-01) [web]    │
│ • McKinsey (2023-08) [web]              │
│ • Internal Report (2024-11) [doc]       │
│                                          │
└─────────────────────────────────────────┘
```

### Claim Status Categories

| Status | Meaning | Presentation |
|--------|---------|-------------|
| `established` | High confidence, no conflicts | Present as fact with source |
| `contested` | Multiple sources disagree | Present all values with attribution |
| `single_source` | Only one source, can't verify | Present with caveat |

### Exam Insight

Synthesis with provenance is about **intellectual honesty**:
1. Never silently discard conflicting information
2. Distinguish certainty levels (established vs. contested vs. single-source)
3. Let the user see the raw evidence behind every claim
4. Annotate what's MISSING (coverage gaps) — silence looks like coverage

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MULTI-AGENT RESEARCH PIPELINE                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ USER REQUEST: "Research enterprise AI adoption"              │     │
│  └──────────────────────────────┬──────────────────────────────┘     │
│                                 │                                     │
│                                 ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ COORDINATOR AGENT                                            │     │
│  │ • Analyzes topic → decomposes into subqueries               │     │
│  │ • Has allowedTools: ["Task"] for spawning subagents          │     │
│  │ • Emits MULTIPLE tool calls in ONE response (parallel)       │     │
│  │ • Passes FULL context in each query (no inheritance)         │     │
│  └──────────┬─────────────────────────────────┬────────────────┘     │
│             │ (parallel)                       │                      │
│             ▼                                  ▼                      │
│  ┌──────────────────────┐        ┌──────────────────────────┐       │
│  │ WEB SEARCH SUBAGENT  │        │ DOCUMENT ANALYSIS SUBAGT │       │
│  │                      │        │                          │       │
│  │ Returns:             │        │ Returns:                 │       │
│  │ • Structured findings│        │ • Structured findings    │       │
│  │ • Source URLs        │        │ • Document references    │       │
│  │ • Confidence scores  │        │ • Confidence scores      │       │
│  │ • OR: error context  │        │                          │       │
│  │   with partial       │        │                          │       │
│  │   results            │        │                          │       │
│  └──────────┬───────────┘        └──────────┬───────────────┘       │
│             │                                │                       │
│             └────────────┬───────────────────┘                       │
│                          │                                            │
│                          ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ SYNTHESIS ENGINE                                             │     │
│  │ • Collects all findings (including partial from errors)      │     │
│  │ • Detects conflicts between sources                          │     │
│  │ • Separates established vs contested findings                │     │
│  │ • Annotates coverage gaps from failed subagents              │     │
│  │ • Preserves full provenance (finding_ids → sources)          │     │
│  └──────────────────────────────┬──────────────────────────────┘     │
│                                 │                                     │
│                                 ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ FINAL REPORT                                                 │     │
│  │ • Established findings (high confidence, no conflicts)       │     │
│  │ • Contested findings (sources disagree, both preserved)      │     │
│  │ • Coverage gaps (what's missing and why)                     │     │
│  │ • Source list (full provenance chain)                        │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways for the Exam

1. **Subagents don't inherit context** — the coordinator must pass everything the subagent needs in its prompt. This is explicit by design, not a limitation. It prevents context pollution and enables independent testing.

2. **Parallel execution = multiple tool_use blocks in one response** — when the coordinator emits 2+ tool calls simultaneously, the orchestration layer can execute them in parallel. Speedup is bounded by the slowest subagent.

3. **Structured findings separate content from metadata** — every claim has a `finding_id`, source, date, and confidence. This enables programmatic conflict detection and provenance tracking through synthesis.

4. **Error propagation must be structured** — include `failure_type`, `partial_results`, `is_retryable`, and `coverage_gap`. This lets the coordinator make informed decisions (retry vs. proceed with partial results).

5. **Graceful degradation over total failure** — when a subagent times out, use its partial results and annotate what's missing. Don't discard work or fail the entire pipeline.

6. **Never silently resolve conflicts** — when sources disagree, preserve BOTH values with full attribution. The report should clearly distinguish "established" from "contested" findings.

7. **Coverage gaps must be explicit** — if a subagent couldn't cover academic sources, say so in the final report. Silence looks like "everything was covered."

8. **Finding IDs enable traceability** — from any claim in the synthesis, you can trace back to the exact source, date, and evidence excerpt. This is essential for user trust and debugging.

9. **Coordinator tools need clear "no inheritance" documentation** — tool descriptions should explicitly state that subagents don't see the coordinator's history. This guides the model to write self-contained queries.

10. **The synthesis is the hardest part** — collecting data is mechanical; deciding what conflicts, what's established, and what's missing requires the most sophisticated logic in the pipeline.
