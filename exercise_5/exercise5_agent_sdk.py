"""
Exercise 5: Build an Agent with the Claude Agent SDK
=====================================================
Demonstrates a complete agentic loop with:
- Tool calling and execution
- Error handling with retries and graceful degradation
- Session management (multi-turn conversation with context window awareness)
- Subagent spawning with explicit context passing
- Tool Runner pattern (decorator-based tool registration)

Run: python exercise_5/exercise5_agent_sdk.py --demo
"""

import json
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed


# =============================================================================
# SECTION 1: Tool Definitions (decorator-based registration like @beta_tool)
# =============================================================================

TOOL_REGISTRY: dict[str, dict] = {}


def register_tool(name: str, description: str, parameters: dict):
    """Decorator to register a tool function (mimics @beta_tool pattern)."""
    def decorator(func):
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": parameters,
                "required": list(parameters.keys()),
            },
            "handler": func,
        }
        return func
    return decorator


@register_tool(
    name="search_knowledge_base",
    description="Search internal knowledge base for articles. Use for factual questions about products, policies, or procedures.",
    parameters={
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "description": "Maximum results to return (1-10)"},
    },
)
def search_knowledge_base(query: str, max_results: int) -> dict:
    articles = {
        "refund policy": [
            {"id": "KB-101", "title": "Refund Policy Overview", "content": "Full refunds within 30 days of purchase. Partial refunds (50%) between 30-60 days. No refunds after 60 days. Digital products are non-refundable after download."},
            {"id": "KB-102", "title": "Refund Exceptions", "content": "Defective items receive full refund regardless of time. Subscription cancellations are prorated to the day."},
        ],
        "shipping": [
            {"id": "KB-201", "title": "Shipping Times", "content": "Standard: 5-7 business days. Express: 2-3 business days. Overnight: next business day. International: 10-14 business days."},
        ],
        "account": [
            {"id": "KB-301", "title": "Account Management", "content": "Password reset via email link. 2FA available via authenticator app. Account deletion takes 30 days (grace period)."},
        ],
    }
    for keyword, results in articles.items():
        if keyword in query.lower():
            return {"results": results[:max_results], "total_found": len(results)}
    return {"results": [], "total_found": 0}


@register_tool(
    name="lookup_order",
    description="Look up order details by order ID. Use when customer asks about a specific order.",
    parameters={
        "order_id": {"type": "string", "description": "Order ID (format: ORD-XXXXX)"},
    },
)
def lookup_order(order_id: str) -> dict:
    orders = {
        "ORD-12345": {"order_id": "ORD-12345", "status": "shipped", "items": ["Widget Pro", "Cable Set"], "total": 89.99, "tracking": "TRK-9876543", "ship_date": "2024-01-15"},
        "ORD-67890": {"order_id": "ORD-67890", "status": "processing", "items": ["Gadget Plus"], "total": 149.99, "tracking": None, "ship_date": None},
    }
    if order_id in orders:
        return {"found": True, "order": orders[order_id]}
    return {"found": False, "error": "Order not found", "suggestion": "Verify the order ID format (ORD-XXXXX)"}


@register_tool(
    name="create_ticket",
    description="Create a support ticket for issues that require human follow-up. Use when the issue cannot be resolved automatically.",
    parameters={
        "subject": {"type": "string", "description": "Ticket subject"},
        "priority": {"type": "string", "description": "Priority: low, medium, high, urgent"},
        "description": {"type": "string", "description": "Detailed description of the issue"},
        "customer_id": {"type": "string", "description": "Customer identifier"},
    },
)
def create_ticket(subject: str, priority: str, description: str, customer_id: str) -> dict:
    ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
    return {"ticket_id": ticket_id, "status": "created", "priority": priority, "estimated_response": "24 hours" if priority in ("low", "medium") else "4 hours"}


@register_tool(
    name="check_inventory",
    description="Check product inventory and availability. Use when customer asks about stock or delivery estimates.",
    parameters={
        "product_name": {"type": "string", "description": "Product name to check"},
    },
)
def check_inventory(product_name: str) -> dict:
    inventory = {
        "widget pro": {"in_stock": True, "quantity": 142, "warehouse": "US-East", "restock_date": None},
        "gadget plus": {"in_stock": False, "quantity": 0, "warehouse": None, "restock_date": "2024-02-15"},
        "cable set": {"in_stock": True, "quantity": 500, "warehouse": "US-West", "restock_date": None},
    }
    key = product_name.lower()
    for name, data in inventory.items():
        if name in key or key in name:
            return {"found": True, "product": name, **data}
    return {"found": False, "error": f"Product '{product_name}' not found in catalog"}


# =============================================================================
# SECTION 2: Session Management
# =============================================================================

@dataclass
class Session:
    """Manages conversation state with context window awareness."""
    session_id: str = field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:8]}")
    messages: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    max_context_tokens: int = 200000
    estimated_tokens_used: int = 0
    turn_count: int = 0
    created_at: float = field(default_factory=time.time)

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self.estimated_tokens_used += len(content) // 4
        self.turn_count += 1

    def add_assistant_message(self, content: list[dict]):
        self.messages.append({"role": "assistant", "content": content})
        self.estimated_tokens_used += sum(len(json.dumps(b)) // 4 for b in content)

    def add_tool_result(self, tool_use_id: str, result: Any):
        self.messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(result)}],
        })
        self.estimated_tokens_used += len(json.dumps(result)) // 4

    def needs_compaction(self) -> bool:
        return self.estimated_tokens_used > self.max_context_tokens * 0.8

    def compact(self) -> str:
        """Summarize older messages to free context window space."""
        if len(self.messages) <= 4:
            return "Nothing to compact"
        older = self.messages[:-4]
        summary_parts = []
        for msg in older:
            if msg["role"] == "user" and isinstance(msg["content"], str):
                summary_parts.append(f"User asked: {msg['content'][:100]}")
            elif msg["role"] == "assistant":
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        summary_parts.append(f"Assistant: {block['text'][:100]}")
        summary = "Previous conversation summary: " + "; ".join(summary_parts[-5:])
        self.messages = [{"role": "user", "content": summary}] + self.messages[-4:]
        self.estimated_tokens_used = sum(
            len(json.dumps(m.get("content", ""))) // 4 for m in self.messages
        )
        return f"Compacted {len(older)} messages into summary"

    def get_messages(self) -> list[dict]:
        return self.messages.copy()


# =============================================================================
# SECTION 3: Error Handling with Classification
# =============================================================================

@dataclass
class AgentError:
    error_type: str  # "transient", "validation", "tool_failure", "context_overflow"
    message: str
    is_retryable: bool
    retry_after_seconds: float = 0
    context: dict = field(default_factory=dict)


def classify_error(error: Exception, attempt: int) -> AgentError:
    error_str = str(error).lower()
    if "rate_limit" in error_str or "429" in error_str:
        return AgentError(
            error_type="transient",
            message="Rate limited by API",
            is_retryable=True,
            retry_after_seconds=min(2 ** attempt, 30),
            context={"attempt": attempt},
        )
    elif "overloaded" in error_str or "529" in error_str:
        return AgentError(
            error_type="transient",
            message="API overloaded",
            is_retryable=True,
            retry_after_seconds=min(2 ** attempt * 2, 60),
            context={"attempt": attempt},
        )
    elif "context" in error_str or "token" in error_str:
        return AgentError(
            error_type="context_overflow",
            message="Context window exceeded",
            is_retryable=True,
            retry_after_seconds=0,
            context={"action": "compact_and_retry"},
        )
    elif "invalid" in error_str or "schema" in error_str:
        return AgentError(
            error_type="validation",
            message=f"Validation error: {error}",
            is_retryable=False,
            context={"original_error": str(error)},
        )
    else:
        return AgentError(
            error_type="tool_failure",
            message=str(error),
            is_retryable=attempt < 3,
            retry_after_seconds=1,
            context={"attempt": attempt},
        )


# =============================================================================
# SECTION 4: The Agentic Loop
# =============================================================================

def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Execute a registered tool and return the result."""
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}", "error_type": "validation"}
    try:
        handler = TOOL_REGISTRY[tool_name]["handler"]
        result = handler(**tool_input)
        return {"success": True, "result": result}
    except TypeError as e:
        return {"error": f"Invalid parameters: {e}", "error_type": "validation"}
    except Exception as e:
        return {"error": str(e), "error_type": "tool_failure"}


def run_agentic_loop(session: Session, system_prompt: str, max_iterations: int = 10, demo_mode: bool = False):
    """
    Core agentic loop: send message → check stop_reason → execute tools → loop.

    The loop continues while stop_reason == "tool_use".
    It terminates when stop_reason == "end_turn" or max iterations reached.
    """
    iteration = 0
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOL_REGISTRY.values()
    ]

    while iteration < max_iterations:
        iteration += 1

        if session.needs_compaction():
            result = session.compact()
            print(f"  [Context management] {result}")

        if demo_mode:
            response = simulate_api_response(session, iteration)
        else:
            response = call_claude_api(session, system_prompt, tools)

        stop_reason = response["stop_reason"]
        content_blocks = response["content"]

        session.add_assistant_message(content_blocks)

        if stop_reason == "end_turn":
            text_blocks = [b for b in content_blocks if b.get("type") == "text"]
            final_text = " ".join(b["text"] for b in text_blocks)
            return {"status": "complete", "response": final_text, "iterations": iteration}

        elif stop_reason == "tool_use":
            tool_calls = [b for b in content_blocks if b.get("type") == "tool_use"]
            print(f"  [Iteration {iteration}] {len(tool_calls)} tool call(s): {[t['name'] for t in tool_calls]}")

            for tool_call in tool_calls:
                tool_result = execute_tool(tool_call["name"], tool_call["input"])
                session.add_tool_result(tool_call["id"], tool_result)
                print(f"    → {tool_call['name']}: {'✓' if tool_result.get('success') else '✗'}")

        else:
            return {"status": "unexpected_stop", "stop_reason": stop_reason, "iterations": iteration}

    return {"status": "max_iterations", "iterations": iteration}


def call_claude_api(session: Session, system_prompt: str, tools: list) -> dict:
    """Call the Claude API (live mode). Requires ANTHROPIC_API_KEY."""
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        tools=tools,
        messages=session.get_messages(),
    )
    content = []
    for block in response.content:
        if block.type == "text":
            content.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return {"stop_reason": response.stop_reason, "content": content}


# =============================================================================
# SECTION 5: Subagent Spawning (Coordinator Pattern)
# =============================================================================

@dataclass
class SubagentTask:
    """A task delegated to a subagent with explicit context."""
    task_id: str
    agent_type: str  # "specialist_lookup", "ticket_handler", "inventory_checker"
    prompt: str  # Self-contained — includes ALL context needed
    context: dict  # Explicit context passed from coordinator
    timeout_seconds: float = 30.0


@dataclass
class SubagentResult:
    task_id: str
    status: str  # "success", "partial", "failed"
    result: Any = None
    error: AgentError | None = None
    duration_ms: float = 0


def spawn_subagent(task: SubagentTask, demo_mode: bool = False) -> SubagentResult:
    """
    Spawn a subagent with explicit context (no inheritance from parent).
    Each subagent gets its own session — it does NOT see the coordinator's history.
    """
    start_time = time.time()

    subagent_session = Session()
    subagent_session.metadata = {
        "parent_task_id": task.task_id,
        "agent_type": task.agent_type,
    }

    subagent_session.add_user_message(task.prompt)

    if demo_mode:
        result = simulate_subagent(task)
    else:
        subagent_system = f"You are a specialized {task.agent_type} agent. Answer the query using only the context provided. Do not assume any information not explicitly given."
        tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in TOOL_REGISTRY.values()
        ]
        result = run_agentic_loop(subagent_session, subagent_system, max_iterations=5, demo_mode=demo_mode)

    duration = (time.time() - start_time) * 1000

    if result.get("status") == "complete":
        return SubagentResult(task_id=task.task_id, status="success", result=result["response"], duration_ms=duration)
    else:
        return SubagentResult(
            task_id=task.task_id,
            status="failed",
            error=AgentError(error_type="tool_failure", message=f"Subagent failed: {result.get('status')}", is_retryable=True),
            duration_ms=duration,
        )


def run_coordinator(user_query: str, customer_id: str, demo_mode: bool = False) -> dict:
    """
    Coordinator pattern: analyze query → spawn subagents → synthesize results.
    Demonstrates explicit context passing and parallel execution.
    """
    print(f"\n{'='*60}")
    print(f"COORDINATOR: Analyzing query...")
    print(f"  Query: \"{user_query}\"")
    print(f"  Customer: {customer_id}")
    print(f"{'='*60}")

    tasks = decompose_query(user_query, customer_id)
    print(f"\n  Decomposed into {len(tasks)} subagent task(s):")
    for t in tasks:
        print(f"    • [{t.agent_type}] {t.prompt[:80]}...")

    print(f"\n  Executing subagents in parallel...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(spawn_subagent, task, demo_mode): task for task in tasks}
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status_icon = "✓" if result.status == "success" else "✗"
            print(f"    {status_icon} [{result.task_id}] completed in {result.duration_ms:.0f}ms")

    parallel_time = (time.time() - start_time) * 1000
    print(f"\n  All subagents completed in {parallel_time:.0f}ms (parallel)")

    synthesis = synthesize_results(results, user_query)
    return synthesis


def decompose_query(query: str, customer_id: str) -> list[SubagentTask]:
    """Coordinator decomposes query into self-contained subagent tasks."""
    tasks = []
    query_lower = query.lower()

    if "order" in query_lower or "ORD-" in query:
        import re
        order_ids = re.findall(r"ORD-\d+", query)
        for oid in order_ids:
            tasks.append(SubagentTask(
                task_id=f"task-{uuid.uuid4().hex[:6]}",
                agent_type="order_lookup",
                prompt=f"Look up order {oid} for customer {customer_id}. Return the full order details including status, items, and tracking information.",
                context={"order_id": oid, "customer_id": customer_id},
            ))

    if any(kw in query_lower for kw in ["refund", "return", "money back"]):
        tasks.append(SubagentTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            agent_type="policy_lookup",
            prompt=f"Search the knowledge base for refund policy information. The customer (ID: {customer_id}) is asking: '{query}'. Provide the relevant policy details.",
            context={"customer_id": customer_id, "topic": "refund"},
        ))

    if any(kw in query_lower for kw in ["stock", "available", "inventory", "in stock"]):
        tasks.append(SubagentTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            agent_type="inventory_check",
            prompt=f"Check inventory for products mentioned in this query: '{query}'. Report availability, quantity, and estimated restock dates if out of stock.",
            context={"customer_id": customer_id},
        ))

    if any(kw in query_lower for kw in ["help", "issue", "problem", "broken", "not working"]):
        tasks.append(SubagentTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            agent_type="ticket_handler",
            prompt=f"Customer {customer_id} has reported an issue: '{query}'. Create a support ticket with appropriate priority and return the ticket ID.",
            context={"customer_id": customer_id, "issue": query},
        ))

    if not tasks:
        tasks.append(SubagentTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            agent_type="general_search",
            prompt=f"Search the knowledge base to answer this customer query: '{query}'. Customer ID: {customer_id}.",
            context={"customer_id": customer_id},
        ))

    return tasks


def synthesize_results(results: list[SubagentResult], original_query: str) -> dict:
    """Synthesize subagent results into a unified response."""
    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status != "success"]

    synthesis = {
        "query": original_query,
        "status": "complete" if not failed else "partial",
        "response_parts": [r.result for r in successful],
        "coverage_gaps": [],
        "total_duration_ms": sum(r.duration_ms for r in results),
    }

    if failed:
        for f in failed:
            synthesis["coverage_gaps"].append({
                "task_id": f.task_id,
                "error": f.error.message if f.error else "Unknown failure",
                "impact": "Some information may be missing from the response",
            })

    return synthesis


# =============================================================================
# SECTION 6: Tool Runner Pattern (automated loop with hooks)
# =============================================================================

@dataclass
class ToolRunnerConfig:
    """Configuration for the tool runner (mimics client.beta.messages.tool_runner)."""
    max_iterations: int = 10
    on_tool_call: Any = None  # Pre-execution hook (approval gate)
    on_tool_result: Any = None  # Post-execution hook (result modification)
    on_error: Any = None  # Error hook (retry logic)


def tool_runner_loop(session: Session, config: ToolRunnerConfig, demo_mode: bool = False) -> dict:
    """
    Tool Runner pattern: SDK-managed loop with per-turn hooks.

    Hooks provide:
    - Approval gates (block dangerous operations)
    - Result modification (add cache_control, redact sensitive data)
    - Error interception (classify and retry)
    """
    iteration = 0
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOL_REGISTRY.values()
    ]

    while iteration < config.max_iterations:
        iteration += 1

        if demo_mode:
            response = simulate_api_response(session, iteration)
        else:
            response = call_claude_api(session, "You are a helpful customer support agent.", tools)

        stop_reason = response["stop_reason"]
        content_blocks = response["content"]
        session.add_assistant_message(content_blocks)

        if stop_reason == "end_turn":
            text = " ".join(b["text"] for b in content_blocks if b.get("type") == "text")
            return {"status": "complete", "response": text, "iterations": iteration}

        tool_calls = [b for b in content_blocks if b.get("type") == "tool_use"]

        for tool_call in tool_calls:
            # Pre-execution hook (approval gate)
            if config.on_tool_call:
                approved = config.on_tool_call(tool_call)
                if not approved:
                    session.add_tool_result(tool_call["id"], {"error": "Tool call blocked by policy", "error_type": "permission"})
                    print(f"    ✗ {tool_call['name']}: BLOCKED by hook")
                    continue

            tool_result = execute_tool(tool_call["name"], tool_call["input"])

            # Post-execution hook (result modification)
            if config.on_tool_result:
                tool_result = config.on_tool_result(tool_call, tool_result)

            session.add_tool_result(tool_call["id"], tool_result)
            print(f"    → {tool_call['name']}: {'✓' if tool_result.get('success') else '✗'}")

    return {"status": "max_iterations", "iterations": iteration}


# =============================================================================
# SECTION 7: Demo Mode Simulation
# =============================================================================

DEMO_SCENARIOS = {
    1: {  # First iteration: tool use
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "Let me look into that for you."},
            {"type": "tool_use", "id": "toolu_01", "name": "search_knowledge_base", "input": {"query": "refund policy", "max_results": 3}},
        ],
    },
    2: {  # Second iteration: another tool call
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "I found the policy. Let me also check your order."},
            {"type": "tool_use", "id": "toolu_02", "name": "lookup_order", "input": {"order_id": "ORD-12345"}},
        ],
    },
    3: {  # Third iteration: end turn with final response
        "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": "Based on my research, here's what I found:\n\n1. **Refund Policy**: Full refunds are available within 30 days of purchase. Since your order ORD-12345 shipped on January 15, you're within the 30-day window.\n\n2. **Your Order**: Order ORD-12345 contains Widget Pro and Cable Set (total: $89.99). It has been shipped with tracking TRK-9876543.\n\n3. **Next Steps**: To initiate a refund, I can create a support ticket for you, or you can return the items using the prepaid label in your shipment.\n\nWould you like me to create a refund ticket?"},
        ],
    },
}


def simulate_api_response(session: Session, iteration: int) -> dict:
    """Simulate Claude API responses for demo mode."""
    if iteration in DEMO_SCENARIOS:
        return DEMO_SCENARIOS[iteration]
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "I've addressed your query. Is there anything else I can help with?"}],
    }


def simulate_subagent(task: SubagentTask) -> dict:
    """Simulate subagent execution for demo mode."""
    time.sleep(0.05 + 0.1 * hash(task.task_id) % 10 / 10)

    if task.agent_type == "order_lookup":
        order_id = task.context.get("order_id", "ORD-12345")
        result = lookup_order(order_id)
        if result["found"]:
            return {"status": "complete", "response": f"Order {order_id}: Status={result['order']['status']}, Items={result['order']['items']}, Total=${result['order']['total']}"}
        return {"status": "complete", "response": f"Order {order_id} not found."}

    elif task.agent_type == "policy_lookup":
        result = search_knowledge_base("refund policy", 3)
        articles = result["results"]
        return {"status": "complete", "response": f"Refund Policy: {articles[0]['content']}" if articles else "No policy found."}

    elif task.agent_type == "inventory_check":
        return {"status": "complete", "response": "Widget Pro: In stock (142 units, US-East). Gadget Plus: Out of stock, restocking 2024-02-15."}

    elif task.agent_type == "ticket_handler":
        ticket = create_ticket("Customer issue", "medium", task.prompt, task.context.get("customer_id", "unknown"))
        return {"status": "complete", "response": f"Ticket created: {ticket['ticket_id']} (priority: {ticket['priority']}, ETA: {ticket['estimated_response']})"}

    else:
        result = search_knowledge_base(task.prompt[:50], 2)
        return {"status": "complete", "response": f"Found {result['total_found']} relevant articles."}


# =============================================================================
# SECTION 8: Main Demo
# =============================================================================

def demo_agentic_loop():
    """Demonstrate the core agentic loop with tool calling."""
    print("\n" + "="*70)
    print("DEMO 1: Core Agentic Loop (stop_reason-driven)")
    print("="*70)
    print("\nThe agentic loop processes tool calls until the model says 'end_turn'.")
    print("Pattern: send → check stop_reason → execute tools → loop\n")

    session = Session()
    session.add_user_message("I want to return my order ORD-12345. What's the refund policy?")

    print(f"  Session: {session.session_id}")
    print(f"  User query: \"I want to return my order ORD-12345. What's the refund policy?\"")
    print(f"  Registered tools: {list(TOOL_REGISTRY.keys())}")
    print()

    result = run_agentic_loop(session, "You are a helpful customer support agent.", demo_mode=True)

    print(f"\n  Loop completed in {result['iterations']} iteration(s)")
    print(f"  Status: {result['status']}")
    print(f"\n  Final response (truncated):")
    print(f"  {result['response'][:200]}...")
    print(f"\n  Session stats: {session.turn_count} turns, ~{session.estimated_tokens_used} tokens used")


def demo_error_handling():
    """Demonstrate error classification and retry logic."""
    print("\n" + "="*70)
    print("DEMO 2: Error Handling with Classification")
    print("="*70)
    print("\nErrors are classified into types with retry guidance.\n")

    test_errors = [
        (Exception("rate_limit_error: too many requests (429)"), 1),
        (Exception("overloaded_error: server busy (529)"), 2),
        (Exception("context window exceeded: too many tokens"), 1),
        (Exception("invalid_request: schema validation failed"), 1),
        (Exception("connection timeout"), 1),
    ]

    for error, attempt in test_errors:
        classified = classify_error(error, attempt)
        retry_str = f"retry in {classified.retry_after_seconds}s" if classified.is_retryable else "DO NOT retry"
        print(f"  Error: {str(error)[:50]}")
        print(f"    → Type: {classified.error_type} | {retry_str}")
        if classified.context.get("action"):
            print(f"    → Action: {classified.context['action']}")
        print()


def demo_session_management():
    """Demonstrate session management with context compaction."""
    print("\n" + "="*70)
    print("DEMO 3: Session Management & Context Compaction")
    print("="*70)
    print("\nSessions track token usage and compact when approaching limits.\n")

    session = Session(max_context_tokens=500)

    messages = [
        "What's your refund policy?",
        "Can I return items after 30 days?",
        "What about my order ORD-12345?",
        "Actually, I also need to check ORD-67890",
        "And is the Widget Pro in stock?",
        "One more question about shipping times",
    ]

    for msg in messages:
        session.add_user_message(msg)
        session.add_assistant_message([{"type": "text", "text": f"Response to: {msg[:30]}..."}])

        if session.needs_compaction():
            result = session.compact()
            print(f"  ⚡ {result}")
            print(f"     Tokens after compaction: ~{session.estimated_tokens_used}/{session.max_context_tokens}")

    print(f"\n  Final session state:")
    print(f"    Session ID: {session.session_id}")
    print(f"    Turns: {session.turn_count}")
    print(f"    Messages in context: {len(session.messages)}")
    print(f"    Estimated tokens: ~{session.estimated_tokens_used}/{session.max_context_tokens}")
    print(f"    Needs compaction: {session.needs_compaction()}")


def demo_subagent_spawning():
    """Demonstrate coordinator → subagent delegation with parallel execution."""
    print("\n" + "="*70)
    print("DEMO 4: Subagent Spawning (Coordinator Pattern)")
    print("="*70)
    print("\nCoordinator decomposes query → spawns subagents with explicit context")
    print("Each subagent gets its own session (NO context inheritance)\n")

    synthesis = run_coordinator(
        user_query="I need a refund for order ORD-12345. Also, is the Gadget Plus in stock?",
        customer_id="CUST-789",
        demo_mode=True,
    )

    print(f"\n  Synthesis Result:")
    print(f"    Status: {synthesis['status']}")
    print(f"    Response parts: {len(synthesis['response_parts'])}")
    for i, part in enumerate(synthesis['response_parts'], 1):
        print(f"      {i}. {part[:100]}...")
    if synthesis['coverage_gaps']:
        print(f"    Coverage gaps: {len(synthesis['coverage_gaps'])}")
        for gap in synthesis['coverage_gaps']:
            print(f"      ⚠ {gap['error']}")
    print(f"    Total duration: {synthesis['total_duration_ms']:.0f}ms")


def demo_tool_runner():
    """Demonstrate the Tool Runner pattern with hooks."""
    print("\n" + "="*70)
    print("DEMO 5: Tool Runner Pattern (SDK-Managed Loop with Hooks)")
    print("="*70)
    print("\nThe Tool Runner automates the loop; hooks provide control points.\n")

    blocked_tools = []

    def approval_hook(tool_call: dict) -> bool:
        """Pre-execution hook: block ticket creation for low-priority issues."""
        if tool_call["name"] == "create_ticket" and tool_call["input"].get("priority") == "low":
            blocked_tools.append(tool_call["name"])
            return False
        return True

    redacted_fields = []

    def result_hook(tool_call: dict, result: dict) -> dict:
        """Post-execution hook: redact sensitive data from results."""
        if tool_call["name"] == "lookup_order" and result.get("success"):
            order = result["result"].get("order", {})
            if "tracking" in order and order["tracking"]:
                order["tracking"] = order["tracking"][:4] + "***"
                redacted_fields.append("tracking")
        return result

    config = ToolRunnerConfig(
        max_iterations=5,
        on_tool_call=approval_hook,
        on_tool_result=result_hook,
    )

    session = Session()
    session.add_user_message("Check my order ORD-12345")

    print(f"  Hooks configured:")
    print(f"    • on_tool_call: blocks low-priority ticket creation")
    print(f"    • on_tool_result: redacts tracking numbers")
    print()

    result = tool_runner_loop(session, config, demo_mode=True)

    print(f"\n  Result: {result['status']} in {result['iterations']} iteration(s)")
    print(f"  Blocked tools: {blocked_tools if blocked_tools else 'none'}")
    print(f"  Redacted fields: {redacted_fields if redacted_fields else 'none'}")


def main():
    demo_mode = "--demo" in sys.argv

    if not demo_mode:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ERROR: Set ANTHROPIC_API_KEY or use --demo mode")
            print("  export ANTHROPIC_API_KEY='sk-ant-...'")
            print("  python exercise_5/exercise5_agent_sdk.py --demo")
            sys.exit(1)

    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  Exercise 5: Build an Agent with the Claude Agent SDK               ║")
    print("║  Complete agentic loop with tools, errors, sessions, & subagents    ║")
    print(f"║  Mode: {'DEMO (simulated)' if demo_mode else 'LIVE (calling Claude API)'}                                       ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    demo_agentic_loop()
    demo_error_handling()
    demo_session_management()
    demo_subagent_spawning()
    demo_tool_runner()

    print("\n" + "="*70)
    print("ALL DEMOS COMPLETE")
    print("="*70)
    print("\nKey patterns demonstrated:")
    print("  1. Agentic loop: while stop_reason == 'tool_use' → execute → loop")
    print("  2. Error handling: classify → retry/degrade based on type")
    print("  3. Session management: track tokens → compact when near limit")
    print("  4. Subagent spawning: explicit context → parallel execution → synthesize")
    print("  5. Tool Runner: SDK-managed loop with pre/post hooks for control")


if __name__ == "__main__":
    main()
