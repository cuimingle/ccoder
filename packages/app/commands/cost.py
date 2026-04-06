"""Cost command handler – shows token usage and estimated costs."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandResult

# Pricing per million tokens (Claude Opus-class)
INPUT_PRICE_PER_M = 15.0
OUTPUT_PRICE_PER_M = 75.0


async def cost_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Display token usage and estimated cost for the current session."""
    input_tokens = context.get("total_input_tokens", 0)
    output_tokens = context.get("total_output_tokens", 0)
    turn_count = context.get("turn_count", 0)

    input_cost = input_tokens * INPUT_PRICE_PER_M / 1_000_000
    output_cost = output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
    total_cost = input_cost + output_cost

    lines = [
        "Session Cost Summary",
        f"  Turns:         {turn_count}",
        f"  Input tokens:  {input_tokens:,}",
        f"  Output tokens: {output_tokens:,}",
        f"  Input cost:    ${input_cost:.4f}",
        f"  Output cost:   ${output_cost:.4f}",
        f"  Total cost:    ${total_cost:.4f}",
    ]
    return CommandResult(text="\n".join(lines))
