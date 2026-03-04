"""Core agent loop: drives a multi-turn conversation with tool use."""

from collections.abc import AsyncGenerator

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.executor import execute_tool
from backend.agent.tools import TOOLS
from backend.config import settings

SYSTEM_PROMPT = """You are an investment analysis assistant helping clients understand
their portfolio performance, risk, and allocation.

Your capabilities:
- Retrieve live portfolio snapshots (market values, P&L, weights)
- Compute performance metrics: annualized return, volatility, Sharpe ratio, max drawdown
- Look up metadata for any stock ticker
- Suggest rebalancing when allocation drifts from targets
- Run mean-variance (Markowitz) optimization

Guidelines:
- Always ground your analysis in data from tools before drawing conclusions.
- Present numbers clearly: use percentages, round to 2 decimal places.
- Do NOT make specific buy/sell recommendations for individual securities.
- Do NOT predict future returns or guarantee any outcome.
- Always remind clients that this is informational analysis, not personalized
  investment advice, and that they should consult a licensed financial advisor
  for major decisions.
- If a tool returns an error, acknowledge it and work with what you have.
- If a question is outside your data (e.g., tax advice, legal matters), say so clearly.
"""

MAX_TOOL_ROUNDS = 6


async def run_agent(
    messages: list[dict],
    db: AsyncSession,
    client_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields text chunks as the agent streams its response.
    Handles multi-turn tool use internally.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    conversation = list(messages)
    tool_rounds = 0

    try:
        while True:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=conversation,
            )

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        yield block.text
                break

            if response.stop_reason == "tool_use":
                tool_rounds += 1

                # Safety cap: if too many tool rounds, force a final answer
                if tool_rounds > MAX_TOOL_ROUNDS:
                    yield "\n\n*Summarising with available data...*\n\n"
                    conversation.append({"role": "assistant", "content": response.content})
                    conversation.append({
                        "role": "user",
                        "content": [{"type": "text", "text": "Please summarise what you have found and give your analysis now."}],
                    })
                    final = await client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        messages=conversation,
                    )
                    for block in final.content:
                        if hasattr(block, "text"):
                            yield block.text
                    break

                conversation.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        yield f"*Fetching {block.name.replace('_', ' ')}...*\n\n"
                        result_str = await execute_tool(block.name, block.input, db)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        })

                conversation.append({"role": "user", "content": tool_results})
            else:
                break

    except anthropic.APIStatusError as e:
        yield f"\n\n**Error from AI service:** {e.message} (status {e.status_code})"
    except anthropic.APIConnectionError:
        yield "\n\n**Error:** Could not connect to the AI service. Check your internet connection."
    except Exception as e:
        yield f"\n\n**Unexpected error:** {str(e)}"
