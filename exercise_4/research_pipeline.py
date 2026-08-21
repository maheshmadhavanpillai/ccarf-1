"""
Exercise 4: Design and Debug a Multi-Agent Research Pipeline
=============================================================
Domains: Domain 1 (Agentic Architecture & Orchestration),
         Domain 2 (Tool Design & MCP Integration),
         Domain 5 (Context Management & Reliability)

This exercise demonstrates:
1. Coordinator agent delegating to subagents with explicit context passing
2. Parallel subagent execution with latency measurement
3. Structured output separating content from metadata (provenance tracking)
4. Error propagation with partial results and coverage gap annotation
5. Conflicting source synthesis preserving attribution

Usage:
  # Demo mode (simulates the full pipeline):
  python research_pipeline.py --demo

  # With API key (calls Claude):
  export ANTHROPIC_API_KEY="sk-ant-..."
  python research_pipeline.py
"""

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# STEP 3: Structured Output Schema for Subagents
# =============================================================================
#
# KEY CONCEPT: Separate CONTENT (what was found) from METADATA (where it came from).
# This enables provenance tracking — every claim can be traced to its source.

@dataclass
class Finding:
    """A single research finding with full provenance."""
    claim: str                    # The factual claim being made
    evidence_excerpt: str         # Direct quote or excerpt supporting the claim
    source_url: str              # URL or document name
    source_name: str             # Human-readable source name
    publication_date: str | None  # When the source was published
    confidence: float            # 0-1, how confident the subagent is
    finding_id: str = ""         # Unique ID for tracking through synthesis

    def __post_init__(self):
        if not self.finding_id:
            self.finding_id = f"F-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "claim": self.claim,
            "evidence_excerpt": self.evidence_excerpt,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "publication_date": self.publication_date,
            "confidence": self.confidence
        }


@dataclass
class SubagentResult:
    """Result from a subagent with metadata about the execution."""
    agent_id: str
    agent_type: str              # "web_search" or "document_analysis"
    query: str                   # What was the subagent asked to research
    findings: list[Finding]      # Structured findings
    execution_time_ms: int       # How long the subagent took
    status: str                  # "success", "partial", "timeout", "error"
    error_context: dict | None = None  # Structured error info if failed
    coverage_notes: str = ""     # What the subagent couldn't cover

    def to_dict(self) -> dict:
        result = {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "query": self.query,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "coverage_notes": self.coverage_notes
        }
        if self.error_context:
            result["error_context"] = self.error_context
        return result


# =============================================================================
# STEP 4: Error Propagation Schema
# =============================================================================
#
# KEY CONCEPT: When a subagent fails, return structured error context —
# not just "it failed" but WHY it failed, WHAT was attempted, and WHAT
# partial results are available.

@dataclass
class SubagentError:
    """Structured error from a subagent failure."""
    failure_type: str        # "timeout", "rate_limit", "source_unavailable", "parse_error"
    attempted_query: str     # What the subagent was trying to do
    partial_results: list[Finding]  # Any findings gathered before failure
    error_message: str       # Human-readable error description
    is_retryable: bool       # Whether the coordinator should retry
    coverage_gap: str        # What information is now missing

    def to_dict(self) -> dict:
        return {
            "failure_type": self.failure_type,
            "attempted_query": self.attempted_query,
            "partial_results_count": len(self.partial_results),
            "partial_results": [f.to_dict() for f in self.partial_results],
            "error_message": self.error_message,
            "is_retryable": self.is_retryable,
            "coverage_gap": self.coverage_gap
        }


# =============================================================================
# STEP 5: Synthesis Output with Conflict Handling
# =============================================================================
#
# KEY CONCEPT: When sources conflict, preserve BOTH values with attribution.
# Never silently pick one. Structure output to distinguish established vs contested.

@dataclass
class SynthesizedClaim:
    """A claim in the final synthesis with provenance and conflict status."""
    claim_text: str
    status: str              # "established", "contested", "single_source"
    supporting_findings: list[str]  # finding_ids that support this claim
    conflicting_findings: list[str]  # finding_ids that contradict
    resolution_note: str | None      # How the conflict was handled

    def to_dict(self) -> dict:
        return {
            "claim": self.claim_text,
            "status": self.status,
            "supporting_finding_ids": self.supporting_findings,
            "conflicting_finding_ids": self.conflicting_findings,
            "resolution_note": self.resolution_note
        }


@dataclass
class SynthesisReport:
    """Final synthesized report with full provenance."""
    topic: str
    established_findings: list[SynthesizedClaim]  # High agreement across sources
    contested_findings: list[SynthesizedClaim]     # Sources disagree
    coverage_gaps: list[str]                        # What couldn't be determined
    all_findings: list[Finding]                     # Raw findings for reference
    source_summary: list[dict]                      # Sources used
    total_execution_time_ms: int

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "established_findings": [f.to_dict() for f in self.established_findings],
            "contested_findings": [f.to_dict() for f in self.contested_findings],
            "coverage_gaps": self.coverage_gaps,
            "source_count": len(self.source_summary),
            "sources": self.source_summary,
            "total_findings": len(self.all_findings),
            "total_execution_time_ms": self.total_execution_time_ms
        }


# =============================================================================
# STEP 1 & 2: Coordinator with Subagent Delegation
# =============================================================================
#
# KEY CONCEPTS:
# - Coordinator has "Task" in allowedTools to spawn subagents
# - Subagents receive research context DIRECTLY in their prompts (no automatic inheritance)
# - Parallel execution: coordinator emits multiple Task calls in one response

# Tool definitions for the coordinator agent
COORDINATOR_TOOLS = [
    {
        "name": "delegate_web_search",
        "description": (
            "Delegate a research query to the web search subagent. "
            "The subagent will search the web for recent, authoritative sources "
            "on the specified topic and return structured findings with provenance. "
            "Provide the full research context in the query — the subagent does NOT "
            "inherit the coordinator's conversation history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific research question for web search. Must be self-contained."
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific aspects to focus on (e.g., ['statistics', 'recent studies'])"
                },
                "max_sources": {
                    "type": "integer",
                    "description": "Maximum number of sources to return (default: 5)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "delegate_document_analysis",
        "description": (
            "Delegate document analysis to the document analysis subagent. "
            "The subagent will analyze specific documents or datasets for relevant "
            "findings. Provide the full context including what documents to analyze "
            "and what to look for — the subagent does NOT inherit conversation history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for in the documents. Must be self-contained."
                },
                "documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Document names or IDs to analyze"
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["statistical", "qualitative", "comparative"],
                    "description": "Type of analysis to perform"
                }
            },
            "required": ["query", "documents"]
        }
    },
    {
        "name": "synthesize_findings",
        "description": (
            "Synthesize findings from multiple subagents into a coherent report. "
            "This tool takes the raw findings from all subagents and produces a "
            "structured synthesis that preserves source attribution, identifies "
            "conflicts between sources, and annotates coverage gaps. "
            "Pass ALL findings including partial results from failed subagents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The overall research topic being synthesized"
                },
                "findings": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "All findings from subagents (as JSON objects)"
                },
                "coverage_gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Known gaps in coverage from failed subagents"
                }
            },
            "required": ["topic", "findings"]
        }
    }
]


# =============================================================================
# Simulated Subagent Execution
# =============================================================================

def execute_web_search_subagent(
    query: str,
    focus_areas: list[str] | None = None,
    max_sources: int = 5,
    simulate_timeout: bool = False
) -> SubagentResult:
    """
    Simulates the web search subagent.
    In production, this would be a separate Claude instance with web search tools.
    """
    agent_id = f"web-{uuid.uuid4().hex[:6]}"
    start_time = time.time()

    # Simulate timeout scenario (Step 4)
    if simulate_timeout:
        time.sleep(0.3)  # Simulate partial work before timeout
        partial_findings = [
            Finding(
                claim="Global AI market was valued at $136.6 billion in 2022",
                evidence_excerpt="The global artificial intelligence market size was valued at USD 136.6 billion in 2022",
                source_url="https://www.grandviewresearch.com/industry-analysis/ai-market",
                source_name="Grand View Research",
                publication_date="2023-04",
                confidence=0.85
            )
        ]
        error = SubagentError(
            failure_type="timeout",
            attempted_query=query,
            partial_results=partial_findings,
            error_message="Subagent timed out after 30s while searching additional sources",
            is_retryable=True,
            coverage_gap="Could not retrieve academic/peer-reviewed sources. Only commercial market research was gathered before timeout."
        )
        elapsed = int((time.time() - start_time) * 1000)
        return SubagentResult(
            agent_id=agent_id,
            agent_type="web_search",
            query=query,
            findings=partial_findings,
            execution_time_ms=elapsed,
            status="partial",
            error_context=error.to_dict(),
            coverage_notes="Timed out before completing full search. Academic sources missing."
        )

    # Normal execution - return mock research findings
    time.sleep(0.2)  # Simulate search latency

    findings = [
        Finding(
            claim="Global AI market is projected to reach $1.81 trillion by 2030",
            evidence_excerpt="The global AI market is projected to reach $1.81 trillion by 2030, growing at a CAGR of 36.6%",
            source_url="https://www.grandviewresearch.com/industry-analysis/ai-market",
            source_name="Grand View Research",
            publication_date="2024-01",
            confidence=0.9
        ),
        Finding(
            claim="AI adoption rate among enterprises reached 35% in 2023",
            evidence_excerpt="According to McKinsey's annual survey, 35% of organizations reported using AI in at least one business function in 2023, up from 20% in 2017",
            source_url="https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai",
            source_name="McKinsey Global Survey",
            publication_date="2023-08",
            confidence=0.92
        ),
        Finding(
            claim="The AI market is expected to reach $407 billion by 2027",
            evidence_excerpt="Revenue in the AI market is projected to reach US$407bn in 2027",
            source_url="https://www.statista.com/outlook/tmo/artificial-intelligence/worldwide",
            source_name="Statista",
            publication_date="2024-02",
            confidence=0.88
        ),
    ]

    elapsed = int((time.time() - start_time) * 1000)
    return SubagentResult(
        agent_id=agent_id,
        agent_type="web_search",
        query=query,
        findings=findings,
        execution_time_ms=elapsed,
        status="success"
    )


def execute_document_analysis_subagent(
    query: str,
    documents: list[str],
    analysis_type: str = "statistical"
) -> SubagentResult:
    """
    Simulates the document analysis subagent.
    In production, this would be a separate Claude instance with file access.
    """
    agent_id = f"doc-{uuid.uuid4().hex[:6]}"
    start_time = time.time()
    time.sleep(0.15)  # Simulate analysis time

    # Return findings from "internal documents"
    findings = [
        Finding(
            claim="AI spending in healthcare alone is expected to reach $45.2 billion by 2026",
            evidence_excerpt="Our analysis of healthcare AI investments shows a projected spend of $45.2B by 2026, driven primarily by diagnostic imaging and drug discovery applications",
            source_url="internal://reports/ai-healthcare-forecast-2024.pdf",
            source_name="Internal Market Analysis Report Q4 2024",
            publication_date="2024-11",
            confidence=0.82
        ),
        Finding(
            claim="Enterprise AI adoption is 55% in large companies (>10K employees) vs 25% in SMBs",
            evidence_excerpt="Stratification by company size reveals 55% adoption in enterprises with >10,000 employees compared to just 25% in small and medium businesses",
            source_url="internal://datasets/enterprise-survey-2024.csv",
            source_name="Annual Enterprise Technology Survey 2024",
            publication_date="2024-09",
            confidence=0.78
        ),
        # Deliberately conflicting finding (Step 5)
        Finding(
            claim="AI adoption rate among enterprises reached 50% in 2023",
            evidence_excerpt="Our survey of 2,000 enterprises found that 50% reported active AI deployments in production in 2023",
            source_url="internal://reports/tech-adoption-survey-2023.pdf",
            source_name="Internal Tech Adoption Survey 2023",
            publication_date="2023-12",
            confidence=0.75
        ),
    ]

    elapsed = int((time.time() - start_time) * 1000)
    return SubagentResult(
        agent_id=agent_id,
        agent_type="document_analysis",
        query=query,
        findings=findings,
        execution_time_ms=elapsed,
        status="success"
    )


# =============================================================================
# STEP 2: Parallel Execution Engine
# =============================================================================
#
# KEY CONCEPT: The coordinator emits multiple Task calls in ONE response.
# We execute them in parallel using threads and measure the latency improvement.

@dataclass
class ExecutionMetrics:
    """Tracks sequential vs parallel execution times."""
    sequential_time_ms: int = 0
    parallel_time_ms: int = 0

    @property
    def speedup(self) -> float:
        if self.parallel_time_ms == 0:
            return 0
        return self.sequential_time_ms / self.parallel_time_ms

    @property
    def time_saved_ms(self) -> int:
        return self.sequential_time_ms - self.parallel_time_ms


def execute_subagents_parallel(tasks: list[dict]) -> tuple[list[SubagentResult], ExecutionMetrics]:
    """
    Execute multiple subagent tasks in parallel.
    Returns results and timing metrics.
    """
    metrics = ExecutionMetrics()

    # Measure sequential (for comparison)
    seq_start = time.time()
    sequential_results = []
    for task in tasks:
        result = _dispatch_task(task)
        sequential_results.append(result)
    metrics.sequential_time_ms = int((time.time() - seq_start) * 1000)

    # Execute in parallel
    par_start = time.time()
    parallel_results = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(_dispatch_task, task): task for task in tasks}
        for future in as_completed(futures):
            parallel_results.append(future.result())
    metrics.parallel_time_ms = int((time.time() - par_start) * 1000)

    return parallel_results, metrics


def _dispatch_task(task: dict) -> SubagentResult:
    """Route a task to the appropriate subagent."""
    if task["type"] == "web_search":
        return execute_web_search_subagent(
            query=task["query"],
            focus_areas=task.get("focus_areas"),
            max_sources=task.get("max_sources", 5),
            simulate_timeout=task.get("simulate_timeout", False)
        )
    elif task["type"] == "document_analysis":
        return execute_document_analysis_subagent(
            query=task["query"],
            documents=task.get("documents", []),
            analysis_type=task.get("analysis_type", "statistical")
        )
    else:
        raise ValueError(f"Unknown task type: {task['type']}")


# =============================================================================
# STEP 5: Synthesis Engine with Conflict Detection
# =============================================================================

def detect_conflicts(findings: list[Finding]) -> list[tuple[Finding, Finding, str]]:
    """
    Detect conflicting claims across findings.
    Returns tuples of (finding_a, finding_b, conflict_description).
    """
    conflicts = []

    # Simple heuristic: look for findings about similar topics with different numbers
    for i, f1 in enumerate(findings):
        for f2 in findings[i + 1:]:
            # Check if both mention "adoption rate" with different percentages
            if "adoption" in f1.claim.lower() and "adoption" in f2.claim.lower():
                if f1.source_name != f2.source_name:
                    conflicts.append((
                        f1, f2,
                        "Both sources report enterprise AI adoption rates but with different values"
                    ))
            # Check for market size projections with different targets
            if "trillion" in f1.claim.lower() and "billion" in f2.claim.lower():
                if "2027" in f1.claim and "2030" in f2.claim:
                    pass  # Different time horizons — not a conflict
                elif "2027" in f1.claim and "2027" in f2.claim:
                    conflicts.append((
                        f1, f2,
                        "Both sources project AI market size for similar timeframes but differ significantly"
                    ))

    return conflicts


def synthesize_report(
    topic: str,
    subagent_results: list[SubagentResult],
    execution_time_ms: int
) -> SynthesisReport:
    """
    Synthesize findings from multiple subagents into a coherent report.
    Preserves attribution, identifies conflicts, annotates coverage gaps.
    """
    # Collect all findings
    all_findings = []
    coverage_gaps = []
    source_summary = []

    for result in subagent_results:
        all_findings.extend(result.findings)

        # Track sources
        for finding in result.findings:
            source_summary.append({
                "name": finding.source_name,
                "url": finding.source_url,
                "date": finding.publication_date,
                "agent": result.agent_type
            })

        # Collect coverage gaps from failed/partial subagents
        if result.status in ("partial", "timeout", "error"):
            gap = result.error_context.get("coverage_gap", "") if result.error_context else ""
            if gap:
                coverage_gaps.append(gap)
            if result.coverage_notes:
                coverage_gaps.append(result.coverage_notes)

    # Detect conflicts
    conflicts = detect_conflicts(all_findings)

    # Build established findings (no conflicts)
    conflicting_finding_ids = set()
    contested_findings = []

    for f1, f2, description in conflicts:
        conflicting_finding_ids.add(f1.finding_id)
        conflicting_finding_ids.add(f2.finding_id)
        contested_findings.append(SynthesizedClaim(
            claim_text=f"AI adoption rate: {f1.source_name} reports different value than {f2.source_name}",
            status="contested",
            supporting_findings=[f1.finding_id],
            conflicting_findings=[f2.finding_id],
            resolution_note=(
                f"Source A ({f1.source_name}, {f1.publication_date}): \"{f1.claim}\" "
                f"vs Source B ({f2.source_name}, {f2.publication_date}): \"{f2.claim}\". "
                f"Difference may be due to survey methodology, sample size, or definition of 'adoption'."
            )
        ))

    # Build established findings (not in any conflict)
    established_findings = []
    for finding in all_findings:
        if finding.finding_id not in conflicting_finding_ids:
            established_findings.append(SynthesizedClaim(
                claim_text=finding.claim,
                status="established" if finding.confidence >= 0.8 else "single_source",
                supporting_findings=[finding.finding_id],
                conflicting_findings=[],
                resolution_note=None
            ))

    # Deduplicate sources
    seen_sources = set()
    unique_sources = []
    for s in source_summary:
        key = s["name"]
        if key not in seen_sources:
            seen_sources.add(key)
            unique_sources.append(s)

    return SynthesisReport(
        topic=topic,
        established_findings=established_findings,
        contested_findings=contested_findings,
        coverage_gaps=coverage_gaps,
        all_findings=all_findings,
        source_summary=unique_sources,
        total_execution_time_ms=execution_time_ms
    )


# =============================================================================
# The Coordinator Agent (Real API Version)
# =============================================================================

def run_coordinator(research_topic: str):
    """
    Runs the coordinator agent that orchestrates subagents.
    The coordinator:
    1. Analyzes the research topic
    2. Delegates to web_search and document_analysis subagents
    3. Handles errors and partial results
    4. Synthesizes findings with conflict detection
    """
    import anthropic
    client = anthropic.Anthropic()

    print(f"\n{'='*60}")
    print(f"RESEARCH TOPIC: {research_topic}")
    print(f"{'='*60}\n")

    system_prompt = (
        "You are a research coordinator agent. Your job is to orchestrate research "
        "by delegating specific queries to specialized subagents. "
        "\n\nIMPORTANT RULES:"
        "\n1. Each subagent receives ONLY what you pass in the query — they do NOT "
        "inherit your conversation. Make queries self-contained."
        "\n2. Emit MULTIPLE delegate calls in one response for parallel execution."
        "\n3. If a subagent returns an error, proceed with partial results and note "
        "coverage gaps in the synthesis."
        "\n4. When synthesizing, preserve ALL source attributions. If sources conflict, "
        "report BOTH values — never silently pick one."
        "\n5. After receiving subagent results, call synthesize_findings to produce "
        "the final report."
    )

    messages = [{"role": "user", "content": f"Research this topic thoroughly: {research_topic}"}]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        tools=COORDINATOR_TOOLS,
        messages=messages
    )

    # Process coordinator's delegation decisions
    if response.stop_reason == "tool_use":
        tasks = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "delegate_web_search":
                    tasks.append({"type": "web_search", **block.input})
                elif block.name == "delegate_document_analysis":
                    tasks.append({"type": "document_analysis", **block.input})

        if tasks:
            results, metrics = execute_subagents_parallel(tasks)
            print(f"Parallel execution: {metrics.parallel_time_ms}ms")
            print(f"Sequential would be: {metrics.sequential_time_ms}ms")
            print(f"Speedup: {metrics.speedup:.1f}x")

            # Synthesize
            report = synthesize_report(research_topic, results, metrics.parallel_time_ms)
            print(f"\n{json.dumps(report.to_dict(), indent=2)}")


# =============================================================================
# DEMO MODE
# =============================================================================

def run_demo():
    """Demonstrates the full multi-agent research pipeline without API calls."""
    print("\n" + "=" * 70)
    print(" EXERCISE 4: Multi-Agent Research Pipeline")
    print(" (DEMO MODE)")
    print("=" * 70)

    research_topic = "Current state of enterprise AI adoption and market projections"

    # ─── STEP 1: Coordinator Delegation ───
    print("\n\n" + "─" * 60)
    print("STEP 1: Coordinator Delegates to Subagents")
    print("─" * 60)

    print(f"\n[Research topic]: {research_topic}")
    print(f"\n[Coordinator analyzes topic and decides on delegation:]")
    print(f"  → Subagent 1: Web Search")
    print(f"    Query: 'AI market size projections 2024-2030, enterprise adoption rates'")
    print(f"    Focus: ['market statistics', 'adoption surveys', 'growth projections']")
    print(f"  → Subagent 2: Document Analysis")
    print(f"    Query: 'Analyze internal reports for AI spending and adoption data'")
    print(f"    Documents: ['ai-healthcare-forecast-2024.pdf', 'enterprise-survey-2024.csv']")

    print(f"\n[KEY PRINCIPLE: Each subagent's prompt is SELF-CONTAINED.]")
    print(f"  The coordinator passes the full research context in the query field.")
    print(f"  Subagents do NOT inherit the coordinator's conversation history.")
    print(f"  This prevents context confusion and enables independent execution.")

    # ─── STEP 2: Parallel Execution ───
    print("\n\n" + "─" * 60)
    print("STEP 2: Parallel Subagent Execution")
    print("─" * 60)

    tasks = [
        {
            "type": "web_search",
            "query": "AI market size projections 2024-2030, enterprise AI adoption rates, growth forecasts",
            "focus_areas": ["market statistics", "adoption surveys", "growth projections"],
            "max_sources": 5
        },
        {
            "type": "document_analysis",
            "query": "Analyze internal reports for AI investment data, adoption rates by company size, and healthcare AI projections",
            "documents": ["ai-healthcare-forecast-2024.pdf", "enterprise-survey-2024.csv", "tech-adoption-survey-2023.pdf"],
            "analysis_type": "statistical"
        }
    ]

    print(f"\n[Coordinator emits 2 Task calls in ONE response (parallel)]")
    print(f"[Executing both subagents simultaneously...]")

    results, metrics = execute_subagents_parallel(tasks)

    print(f"\n[Execution metrics:]")
    print(f"  Parallel time:    {metrics.parallel_time_ms}ms")
    print(f"  Sequential time:  {metrics.sequential_time_ms}ms")
    print(f"  Speedup:          {metrics.speedup:.2f}x")
    print(f"  Time saved:       {metrics.time_saved_ms}ms")

    # ─── STEP 3: Structured Output ───
    print("\n\n" + "─" * 60)
    print("STEP 3: Structured Output with Provenance")
    print("─" * 60)

    print(f"\n[Subagent results separate content from metadata:]")
    for result in results:
        print(f"\n  Agent: {result.agent_id} ({result.agent_type})")
        print(f"  Status: {result.status}")
        print(f"  Findings: {len(result.findings)}")
        for finding in result.findings[:2]:  # Show first 2
            print(f"\n    Finding {finding.finding_id}:")
            print(f"      Claim: {finding.claim}")
            print(f"      Evidence: \"{finding.evidence_excerpt[:80]}...\"")
            print(f"      Source: {finding.source_name}")
            print(f"      URL: {finding.source_url}")
            print(f"      Date: {finding.publication_date}")
            print(f"      Confidence: {finding.confidence}")
        if len(result.findings) > 2:
            print(f"\n    ... and {len(result.findings) - 2} more findings")

    # ─── STEP 4: Error Propagation ───
    print("\n\n" + "─" * 60)
    print("STEP 4: Error Propagation (Simulated Timeout)")
    print("─" * 60)

    print(f"\n[Simulating a subagent timeout scenario...]")

    timeout_task = {
        "type": "web_search",
        "query": "Academic peer-reviewed studies on AI adoption methodology",
        "focus_areas": ["peer-reviewed", "methodology"],
        "simulate_timeout": True
    }
    timeout_result = _dispatch_task(timeout_task)

    print(f"\n[Subagent returned with status: {timeout_result.status}]")
    print(f"\n[Structured error context:]")
    print(json.dumps(timeout_result.error_context, indent=2))

    print(f"\n[Coordinator's response to error:]")
    print(f"  1. Accepts partial results ({len(timeout_result.findings)} finding(s) gathered before timeout)")
    print(f"  2. Records coverage gap: '{timeout_result.error_context['coverage_gap']}'")
    print(f"  3. Annotates final report with what's missing")
    print(f"  4. Does NOT retry (could, since is_retryable=True, but proceeding with partial)")

    # Add the timeout result to our results for synthesis
    all_results = results + [timeout_result]

    # ─── STEP 5: Synthesis with Conflict Detection ───
    print("\n\n" + "─" * 60)
    print("STEP 5: Synthesis with Conflict Detection")
    print("─" * 60)

    total_time = metrics.parallel_time_ms + timeout_result.execution_time_ms
    report = synthesize_report(research_topic, all_results, total_time)

    print(f"\n[Conflict detection:]")
    all_findings = []
    for r in all_results:
        all_findings.extend(r.findings)

    conflicts = detect_conflicts(all_findings)
    if conflicts:
        for f1, f2, desc in conflicts:
            print(f"\n  CONFLICT DETECTED:")
            print(f"    Source A: {f1.source_name} ({f1.publication_date})")
            print(f"      Claim: \"{f1.claim}\"")
            print(f"    Source B: {f2.source_name} ({f2.publication_date})")
            print(f"      Claim: \"{f2.claim}\"")
            print(f"    Description: {desc}")
    else:
        print(f"  No conflicts detected.")

    print(f"\n[Final Synthesis Report:]")
    print(f"\n  Topic: {report.topic}")

    print(f"\n  ESTABLISHED FINDINGS ({len(report.established_findings)}):")
    for claim in report.established_findings:
        print(f"    [{claim.status.upper()}] {claim.claim_text}")
        print(f"      Supported by: {claim.supporting_findings}")

    print(f"\n  CONTESTED FINDINGS ({len(report.contested_findings)}):")
    for claim in report.contested_findings:
        print(f"    [{claim.status.upper()}] {claim.claim_text}")
        print(f"      Resolution: {claim.resolution_note}")

    print(f"\n  COVERAGE GAPS ({len(report.coverage_gaps)}):")
    for gap in report.coverage_gaps:
        print(f"    ⚠ {gap}")

    print(f"\n  SOURCES ({len(report.source_summary)}):")
    for source in report.source_summary:
        print(f"    • {source['name']} ({source['date']}) [{source['agent']}]")

    print(f"\n  Execution time: {report.total_execution_time_ms}ms")

    # ─── Full report JSON ───
    print(f"\n\n[Complete report as JSON:]")
    print(json.dumps(report.to_dict(), indent=2))

    print("\n\n" + "=" * 70)
    print(" PIPELINE COMPLETE")
    print("=" * 70)


# =============================================================================
# MAIN
# =============================================================================

def main():
    if "--demo" in sys.argv:
        run_demo()
    else:
        run_coordinator(
            "Current state of enterprise AI adoption and market projections for 2024-2030"
        )


if __name__ == "__main__":
    main()
