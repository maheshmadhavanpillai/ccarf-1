"""
Exercise 1: Multi-Tool Agent with Escalation Logic
====================================================
Domains: Agentic Architecture, Tool Design & MCP Integration, Context Management & Reliability

This exercise demonstrates:
1. MCP tool definitions with clear differentiation
2. Agentic loop with stop_reason handling
3. Structured error responses with retry logic
4. Programmatic hooks enforcing business rules (escalation)
5. Multi-concern message decomposition

Usage:
  # With a real API key (calls Claude):
  export ANTHROPIC_API_KEY="sk-ant-..."
  python exercise1_multi_tool_agent.py

  # Demo mode (simulates the agentic loop without API calls):
  python exercise1_multi_tool_agent.py --demo
"""

import json
import sys
import time
from typing import Any

# =============================================================================
# STEP 1: Define MCP Tools with Detailed Descriptions
# =============================================================================
#
# KEY ARCHITECTURE CONCEPT: Tool descriptions are the primary mechanism for
# Claude to decide WHICH tool to call. Think of them as "routing instructions."
#
# Design principles applied here:
# - Explicitly state what the tool IS for and what it is NOT for
# - Call out boundary conditions (e.g., "max 90 days")
# - Differentiate similar tools explicitly ("use X instead of Y for...")
# - Document side effects (e.g., "confirmation sent to OLD email")
#
# Notice: check_balance and get_transaction_history both access account data
# but serve different purposes. Without clear descriptions, the model might
# confuse them (a common pitfall in tool design).

TOOLS = [
    {
        "name": "check_balance",
        "description": (
            "Retrieves the CURRENT available balance for a customer's account. "
            "Use this when the user asks about how much money they have RIGHT NOW. "
            "This returns a single number representing available funds. "
            "Do NOT use this for historical data or past transactions - use "
            "get_transaction_history instead. "
            "Do NOT use this to initiate any money movement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "The customer's account ID (format: ACC-XXXXX)"
                }
            },
            "required": ["account_id"]
        }
    },
    {
        "name": "get_transaction_history",
        "description": (
            "Retrieves PAST transactions for a customer's account within a date range. "
            "Use this when the user asks about previous spending, deposits, or wants "
            "to review what happened in their account over time. "
            "This returns a LIST of transactions with dates, amounts, and descriptions. "
            "Do NOT use this to check current balance - use check_balance instead. "
            "Do NOT use this to initiate transfers or payments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "The customer's account ID (format: ACC-XXXXX)"
                },
                "days_back": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve (max 90)"
                }
            },
            "required": ["account_id", "days_back"]
        }
    },
    {
        "name": "transfer_funds",
        "description": (
            "Initiates a money transfer FROM one account TO another account. "
            "Use this ONLY when the user explicitly requests to move money. "
            "This is an irreversible action - always confirm the amount and "
            "destination with the user before calling. "
            "Transfers above $10,000 require additional approval and may be "
            "escalated to a human supervisor. "
            "Returns a confirmation with transfer ID or an error if insufficient funds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_account": {
                    "type": "string",
                    "description": "Source account ID (format: ACC-XXXXX)"
                },
                "to_account": {
                    "type": "string",
                    "description": "Destination account ID (format: ACC-XXXXX)"
                },
                "amount": {
                    "type": "number",
                    "description": "Amount to transfer in USD (must be positive)"
                },
                "memo": {
                    "type": "string",
                    "description": "Optional description for the transfer"
                }
            },
            "required": ["from_account", "to_account", "amount"]
        }
    },
    {
        "name": "update_contact_info",
        "description": (
            "Updates a customer's contact information (email, phone, or address). "
            "Use this when the user wants to change their personal details on file. "
            "Only ONE field can be updated per call - if the user wants to update "
            "multiple fields, call this tool once for each field. "
            "Changes take effect immediately and a confirmation notification is "
            "sent to the OLD contact method for security."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "The customer's account ID (format: ACC-XXXXX)"
                },
                "field": {
                    "type": "string",
                    "enum": ["email", "phone", "address"],
                    "description": "Which contact field to update"
                },
                "new_value": {
                    "type": "string",
                    "description": "The new value for the contact field"
                }
            },
            "required": ["account_id", "field", "new_value"]
        }
    }
]


# =============================================================================
# STEP 3: Structured Error Responses
# =============================================================================
#
# KEY ARCHITECTURE CONCEPT: Structured errors allow the agent to make
# programmatic decisions about how to handle failures:
# - "transient" + retryable=True  -> Agent retries automatically
# - "validation" + retryable=False -> Agent explains the issue to user
# - "permission" + retryable=False -> Agent informs user about escalation
#
# This is much better than raw error strings because:
# 1. The agent can take different code paths per error type
# 2. Retry logic is deterministic (not dependent on model interpretation)
# 3. Human-readable descriptions are always available for the user

def create_error_response(category: str, is_retryable: bool, description: str) -> dict:
    """Create a structured error response following our error schema."""
    return {
        "error": True,
        "errorCategory": category,  # transient, validation, permission
        "isRetryable": is_retryable,
        "description": description
    }


def create_success_response(data: dict) -> dict:
    """Create a successful tool response."""
    return {"error": False, "data": data}


# =============================================================================
# STEP 4: Programmatic Hook - Business Rule Enforcement
# =============================================================================
#
# KEY ARCHITECTURE CONCEPT: Hooks run OUTSIDE the model's control.
# This is critical because:
# - The model cannot be prompt-injected into bypassing this check
# - The business rule is deterministic and auditable
# - It's a "hard guardrail" vs. relying on the model to self-police
#
# Pattern: Intercept -> Check -> Allow or Block+Escalate
# This runs BEFORE the tool executes, so blocked operations never reach
# the backend system.

TRANSFER_THRESHOLD = 10000.00

def escalation_hook(tool_name: str, tool_input: dict) -> dict | None:
    """
    Intercepts tool calls to enforce business rules.
    Returns None if the call is allowed to proceed.
    Returns an escalation response dict if the call is blocked.
    """
    if tool_name == "transfer_funds":
        amount = tool_input.get("amount", 0)
        if amount > TRANSFER_THRESHOLD:
            return create_error_response(
                category="permission",
                is_retryable=False,
                description=(
                    f"Transfer of ${amount:,.2f} exceeds the ${TRANSFER_THRESHOLD:,.2f} "
                    f"automatic approval limit. This request has been escalated to a "
                    f"human supervisor for review. Reference ID: ESC-{int(time.time())}. "
                    f"The customer will be notified within 2 business hours."
                )
            )
    return None


# =============================================================================
# Simulated Tool Execution (mock backend)
# =============================================================================

MOCK_ACCOUNTS = {
    "ACC-12345": {"balance": 15420.50, "name": "Alice Johnson", "email": "alice@example.com"},
    "ACC-67890": {"balance": 3200.00, "name": "Bob Smith", "email": "bob@example.com"},
}

MOCK_TRANSACTIONS = [
    {"date": "2025-01-15", "amount": -45.99, "description": "Amazon purchase"},
    {"date": "2025-01-14", "amount": -12.50, "description": "Coffee shop"},
    {"date": "2025-01-13", "amount": 2500.00, "description": "Direct deposit"},
    {"date": "2025-01-12", "amount": -89.00, "description": "Electric bill"},
    {"date": "2025-01-10", "amount": -200.00, "description": "ATM withdrawal"},
]

_transient_error_simulated = False

def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Simulates tool execution with realistic error scenarios.
    In production, these would call actual MCP servers via the transport layer.
    """
    global _transient_error_simulated

    # Simulate a transient error ONCE (to demonstrate retry logic)
    if not _transient_error_simulated and tool_name == "get_transaction_history":
        _transient_error_simulated = True
        return create_error_response(
            category="transient",
            is_retryable=True,
            description="Database connection timeout. Please retry."
        )

    if tool_name == "check_balance":
        account_id = tool_input["account_id"]
        if account_id not in MOCK_ACCOUNTS:
            return create_error_response(
                category="validation",
                is_retryable=False,
                description=f"Account {account_id} not found. Please verify the account ID."
            )
        return create_success_response({
            "account_id": account_id,
            "available_balance": MOCK_ACCOUNTS[account_id]["balance"],
            "currency": "USD"
        })

    elif tool_name == "get_transaction_history":
        account_id = tool_input["account_id"]
        days_back = tool_input.get("days_back", 30)
        if days_back > 90:
            return create_error_response(
                category="validation",
                is_retryable=False,
                description="Cannot retrieve more than 90 days of history."
            )
        if account_id not in MOCK_ACCOUNTS:
            return create_error_response(
                category="validation",
                is_retryable=False,
                description=f"Account {account_id} not found."
            )
        return create_success_response({
            "account_id": account_id,
            "transactions": MOCK_TRANSACTIONS[:max(1, days_back // 3)],
            "period_days": days_back
        })

    elif tool_name == "transfer_funds":
        from_acc = tool_input["from_account"]
        to_acc = tool_input["to_account"]
        amount = tool_input["amount"]
        if from_acc not in MOCK_ACCOUNTS:
            return create_error_response(
                category="validation",
                is_retryable=False,
                description=f"Source account {from_acc} not found."
            )
        if MOCK_ACCOUNTS[from_acc]["balance"] < amount:
            return create_error_response(
                category="validation",
                is_retryable=False,
                description=f"Insufficient funds. Available: ${MOCK_ACCOUNTS[from_acc]['balance']:,.2f}"
            )
        return create_success_response({
            "transfer_id": f"TXN-{int(time.time())}",
            "amount": amount,
            "from": from_acc,
            "to": to_acc,
            "status": "completed"
        })

    elif tool_name == "update_contact_info":
        account_id = tool_input["account_id"]
        if account_id not in MOCK_ACCOUNTS:
            return create_error_response(
                category="validation",
                is_retryable=False,
                description=f"Account {account_id} not found."
            )
        return create_success_response({
            "account_id": account_id,
            "field_updated": tool_input["field"],
            "new_value": tool_input["new_value"],
            "confirmation_sent_to": MOCK_ACCOUNTS[account_id]["email"]
        })

    return create_error_response(
        category="validation",
        is_retryable=False,
        description=f"Unknown tool: {tool_name}"
    )


# =============================================================================
# STEP 2: The Agentic Loop (Real API Version)
# =============================================================================
#
# KEY ARCHITECTURE CONCEPT: The agentic loop pattern
#
#   User Message -> Claude -> [stop_reason check]
#                                |
#                   "tool_use"   |   "end_turn"
#                       |        |        |
#                  Execute tools  |   Return final text
#                       |        |
#                  Send results back to Claude (loop)
#
# The stop_reason is the CONTROL SIGNAL that drives the loop:
# - "tool_use": Claude needs to call a tool. We execute it and feed results back.
# - "end_turn": Claude has composed its final answer. We return it to the user.
#
# This is NOT a simple request-response. It's a LOOP that can run multiple
# iterations as Claude decomposes complex requests into sequential tool calls.

MAX_RETRIES = 2
MAX_ITERATIONS = 10

def run_agent(user_message: str):
    """Runs the agentic loop with the real Anthropic API."""
    import anthropic
    client = anthropic.Anthropic()

    print(f"\n{'='*60}")
    print(f"USER: {user_message}")
    print(f"{'='*60}\n")

    messages = [{"role": "user", "content": user_message}]

    system_prompt = (
        "You are a helpful banking assistant. You have access to tools for "
        "checking balances, viewing transaction history, transferring funds, "
        "and updating contact information. "
        "When a user's request involves multiple concerns, address each one "
        "systematically and provide a unified summary at the end. "
        "If a tool returns an error, explain it clearly to the user. "
        "If an error is marked as retryable, you may retry the operation. "
        "For permission errors (like escalation), inform the user about the "
        "escalation process and what to expect next."
    )

    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"--- Iteration {iteration} ---")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages
        )

        print(f"Stop reason: {response.stop_reason}")

        # ---- STOP REASON: end_turn ----
        # Claude is done. Extract text and return.
        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            print(f"\nASSISTANT: {final_text}")
            return final_text

        # ---- STOP REASON: tool_use ----
        # Claude wants to call one or more tools.
        elif response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    print(f"  Tool call: {tool_name}({json.dumps(tool_input)})")

                    # HOOK: Check business rules BEFORE execution
                    hook_result = escalation_hook(tool_name, tool_input)
                    if hook_result is not None:
                        print(f"  >> HOOK BLOCKED: {hook_result['description']}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(hook_result)
                        })
                        continue

                    # Execute with retry logic
                    result = None
                    for attempt in range(MAX_RETRIES + 1):
                        result = execute_tool(tool_name, tool_input)
                        if result.get("error") and result.get("isRetryable"):
                            if attempt < MAX_RETRIES:
                                print(f"  >> Transient error, retrying ({attempt + 1}/{MAX_RETRIES})...")
                                time.sleep(0.5)
                                continue
                            else:
                                print(f"  >> Max retries exhausted.")
                        break

                    print(f"  Result: {json.dumps(result)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result)
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            print(f"Unexpected stop_reason: {response.stop_reason}")
            break

    print("Max iterations reached.")
    return None


# =============================================================================
# DEMO MODE: Simulates the Agentic Loop Without API Calls
# =============================================================================
# This lets you study the architecture without needing an API key.
# It simulates what Claude would do at each step.

def run_agent_demo(user_message: str, scenario: str):
    """
    Simulates the agentic loop to demonstrate the architecture.
    Shows exactly what happens at each step without calling the API.
    """
    print(f"\n{'='*60}")
    print(f"USER: {user_message}")
    print(f"{'='*60}\n")

    if scenario == "single_balance":
        # Simulated iteration 1: Claude decides to call check_balance
        print("--- Iteration 1 ---")
        print("  [Claude receives message + tool definitions]")
        print("  [Claude decides: user wants current balance -> check_balance tool]")
        print(f"  Stop reason: tool_use")
        print()

        tool_input = {"account_id": "ACC-12345"}
        print(f"  Tool call: check_balance({json.dumps(tool_input)})")

        # Run hook (passes - no escalation needed for balance checks)
        hook_result = escalation_hook("check_balance", tool_input)
        print(f"  Hook check: {'PASSED (no restriction)' if hook_result is None else 'BLOCKED'}")

        # Execute tool
        result = execute_tool("check_balance", tool_input)
        print(f"  Result: {json.dumps(result, indent=4)}")
        print()

        # Simulated iteration 2: Claude composes final answer
        print("--- Iteration 2 ---")
        print("  [Claude receives tool result, composes final answer]")
        print(f"  Stop reason: end_turn")
        print()
        print("  ASSISTANT: Your account ACC-12345 currently has an available")
        print("  balance of $15,420.50 USD.")

    elif scenario == "multi_concern":
        # Multi-concern: balance + history + contact update
        print("--- Iteration 1 ---")
        print("  [Claude decomposes request into 3 concerns]")
        print("  [Claude calls check_balance AND get_transaction_history in parallel]")
        print(f"  Stop reason: tool_use")
        print()

        # Tool 1: check_balance
        tool_input_1 = {"account_id": "ACC-12345"}
        print(f"  Tool call 1: check_balance({json.dumps(tool_input_1)})")
        hook_result = escalation_hook("check_balance", tool_input_1)
        print(f"  Hook check: PASSED")
        result_1 = execute_tool("check_balance", tool_input_1)
        print(f"  Result: {json.dumps(result_1)}")
        print()

        # Tool 2: get_transaction_history (will hit transient error)
        tool_input_2 = {"account_id": "ACC-12345", "days_back": 7}
        print(f"  Tool call 2: get_transaction_history({json.dumps(tool_input_2)})")
        hook_result = escalation_hook("get_transaction_history", tool_input_2)
        print(f"  Hook check: PASSED")

        # First attempt - transient error
        result_2 = execute_tool("get_transaction_history", tool_input_2)
        print(f"  Result (attempt 1): {json.dumps(result_2)}")
        print(f"  >> Error category: {result_2['errorCategory']}, retryable: {result_2['isRetryable']}")
        print(f"  >> Transient error detected - RETRYING (1/{MAX_RETRIES})...")
        time.sleep(0.3)

        # Second attempt - success
        result_2 = execute_tool("get_transaction_history", tool_input_2)
        print(f"  Result (attempt 2): {json.dumps(result_2)}")
        print()

        print("--- Iteration 2 ---")
        print("  [Claude now calls update_contact_info for the email change]")
        print(f"  Stop reason: tool_use")
        print()

        # Tool 3: update_contact_info
        tool_input_3 = {"account_id": "ACC-12345", "field": "email", "new_value": "newalice@example.com"}
        print(f"  Tool call 3: update_contact_info({json.dumps(tool_input_3)})")
        hook_result = escalation_hook("update_contact_info", tool_input_3)
        print(f"  Hook check: PASSED")
        result_3 = execute_tool("update_contact_info", tool_input_3)
        print(f"  Result: {json.dumps(result_3)}")
        print()

        # Final synthesis
        print("--- Iteration 3 ---")
        print("  [Claude synthesizes results from all 3 tools into unified response]")
        print(f"  Stop reason: end_turn")
        print()
        print("  ASSISTANT: Here's a summary of everything for account ACC-12345:")
        print()
        print("  1. **Current Balance**: $15,420.50 USD")
        print()
        print("  2. **Recent Transactions (7 days)**:")
        print("     - Jan 15: Amazon purchase (-$45.99)")
        print("     - Jan 14: Coffee shop (-$12.50)")
        print()
        print("  3. **Email Updated**: Changed to newalice@example.com.")
        print("     A confirmation was sent to your previous email (alice@example.com)")
        print("     for security purposes.")

    elif scenario == "escalation":
        print("--- Iteration 1 ---")
        print("  [Claude decides: user wants a transfer -> transfer_funds tool]")
        print(f"  Stop reason: tool_use")
        print()

        tool_input = {"from_account": "ACC-12345", "to_account": "ACC-67890", "amount": 15000.00}
        print(f"  Tool call: transfer_funds({json.dumps(tool_input)})")

        # HOOK BLOCKS THIS
        hook_result = escalation_hook("transfer_funds", tool_input)
        print(f"  >> HOOK INTERCEPTED!")
        print(f"  >> Business rule: amount ${tool_input['amount']:,.2f} > threshold ${TRANSFER_THRESHOLD:,.2f}")
        print(f"  >> Action: BLOCKED - escalated to human supervisor")
        print(f"  >> Response sent to Claude: {json.dumps(hook_result, indent=4)}")
        print()

        # Claude explains escalation to user
        print("--- Iteration 2 ---")
        print("  [Claude receives permission error, explains escalation to user]")
        print(f"  Stop reason: end_turn")
        print()
        print("  ASSISTANT: I'm unable to process this transfer automatically.")
        print(f"  Your request to transfer $15,000.00 exceeds our automatic")
        print(f"  approval limit of $10,000.00. Here's what happens next:")
        print()
        print(f"  - Your transfer has been escalated to a human supervisor")
        print(f"  - Reference ID: ESC-{int(time.time())}")
        print(f"  - You'll receive a notification within 2 business hours")
        print(f"  - No funds have been moved from your account yet")

    elif scenario == "validation_error":
        print("--- Iteration 1 ---")
        print("  [Claude calls check_balance with the provided account ID]")
        print(f"  Stop reason: tool_use")
        print()

        tool_input = {"account_id": "ACC-99999"}
        print(f"  Tool call: check_balance({json.dumps(tool_input)})")
        hook_result = escalation_hook("check_balance", tool_input)
        print(f"  Hook check: PASSED")
        result = execute_tool("check_balance", tool_input)
        print(f"  Result: {json.dumps(result, indent=4)}")
        print(f"  >> Error category: {result['errorCategory']}")
        print(f"  >> Retryable: {result['isRetryable']} (validation errors are NOT retried)")
        print()

        print("--- Iteration 2 ---")
        print("  [Claude explains the validation error to the user]")
        print(f"  Stop reason: end_turn")
        print()
        print("  ASSISTANT: I wasn't able to retrieve the balance for account")
        print("  ACC-99999. That account ID doesn't appear to exist in our system.")
        print("  Could you double-check the account number? The format should be")
        print("  ACC-XXXXX (e.g., ACC-12345).")


# =============================================================================
# STEP 5: Test with Multi-Concern Messages
# =============================================================================

def main():
    demo_mode = "--demo" in sys.argv

    print("\n" + "=" * 70)
    print(" EXERCISE 1: Multi-Tool Agent with Escalation Logic")
    if demo_mode:
        print(" (DEMO MODE - simulated responses, no API key needed)")
    else:
        print(" (LIVE MODE - calling Claude API)")
    print("=" * 70)

    if demo_mode:
        # Demo mode: simulates the loop behavior
        print("\n\n>>> TEST 1: Single concern (balance check)")
        run_agent_demo(
            "What's the current balance on account ACC-12345?",
            "single_balance"
        )

        print("\n\n>>> TEST 2: Multi-concern message (decomposition + synthesis)")
        run_agent_demo(
            "I need help with my account ACC-12345. Can you: "
            "1) Check my current balance, "
            "2) Show me the last 7 days of transactions, and "
            "3) Update my email to newalice@example.com?",
            "multi_concern"
        )

        print("\n\n>>> TEST 3: Escalation trigger (high-value transfer)")
        run_agent_demo(
            "Please transfer $15,000 from ACC-12345 to ACC-67890 for the "
            "quarterly vendor payment.",
            "escalation"
        )

        print("\n\n>>> TEST 4: Validation error handling")
        run_agent_demo(
            "What's the balance on account ACC-99999?",
            "validation_error"
        )

    else:
        # Live mode: calls the real API
        global _transient_error_simulated

        print("\n\n>>> TEST 1: Single concern (balance check)")
        run_agent("What's the current balance on account ACC-12345?")

        print("\n\n>>> TEST 2: Multi-concern message (decomposition + synthesis)")
        _transient_error_simulated = False  # Reset for this test
        run_agent(
            "I need help with my account ACC-12345. Can you: "
            "1) Check my current balance, "
            "2) Show me the last 7 days of transactions, and "
            "3) Update my email to newalice@example.com?"
        )

        print("\n\n>>> TEST 3: Escalation trigger (high-value transfer)")
        run_agent(
            "Please transfer $15,000 from ACC-12345 to ACC-67890 for the "
            "quarterly vendor payment."
        )

        print("\n\n>>> TEST 4: Validation error handling")
        run_agent("What's the balance on account ACC-99999?")


if __name__ == "__main__":
    main()
