"""
rook.router.orchestrator — Intent routing and agent loop
==========================================================
Classifies user intent, selects model, runs agentic tool-use loop.

Usage:
    from rook.router.orchestrator import handle

    reply = await handle("What's on my calendar today?", system_prompt)
"""

import logging

from rook.core.llm import llm
from rook.core.config import cfg
from rook.skills.loader import get_all_tools, execute_tool

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 12


async def handle(
    user_text: str,
    system: str,
    max_iterations: int = MAX_ITERATIONS,
    tools: list[dict] = None,
    model: str = None,
    history: list[dict] = None,
) -> str:
    """
    Main agentic loop.
    1. Send user message + tools to LLM (with conversation history)
    2. If LLM returns tool_use → execute → send result back
    3. Repeat until LLM returns text-only response
    """
    active_tools = tools if tools is not None else get_all_tools()
    model = model or cfg.main_model

    # Sestav messages z historie + aktuální zpráva
    messages: list[dict] = []
    if history:
        for msg in history[:-1]:  # vše kromě poslední (= aktuální user_text)
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    for iteration in range(max_iterations):
        response = await llm.chat_with_tools(
            messages=messages,
            tools=active_tools,
            system=system,
            model=model,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        # No tool use → final response
        if not tool_use_blocks:
            reply = "".join(b.text for b in text_blocks)
            return reply.strip() or "(no response)"

        # Execute tools
        logger.info(f"Iteration {iteration + 1}: tools={[b.name for b in tool_use_blocks]}")
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            result = await execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })

        messages.append({"role": "user", "content": tool_results})

    # Exceeded iterations
    final = "".join(b.text for b in text_blocks) if text_blocks else ""
    return f"[Reached {max_iterations} iterations]\n{final}".strip()
