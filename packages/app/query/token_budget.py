"""Token budget tracking with diminishing returns detection.

Matches TypeScript ``query/tokenBudget.ts`` behavior:
- Track token consumption across agentic loop iterations
- Detect diminishing returns (model producing minimal output)
- Decide whether to continue or stop the loop
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

COMPLETION_THRESHOLD = 0.90  # Stop at 90% of budget
DIMINISHING_THRESHOLD = 500  # tokens — delta below this is "diminishing"
MIN_CONTINUATIONS_FOR_DIMINISHING = 3


@dataclass
class BudgetTracker:
    """Tracks token budget consumption across query loop iterations."""
    total_budget: int | None = None  # None = unlimited
    continuation_count: int = 0
    last_delta_tokens: int = 0
    last_global_turn_tokens: int = 0
    started_at: float = field(default_factory=time.time)


@dataclass
class BudgetContinue:
    """Decision: continue the loop with a nudge message."""
    action: str = field(default="continue", init=False)
    nudge_message: str = ""
    pct: int = 0
    turn_tokens: int = 0
    budget: int = 0


@dataclass
class BudgetStop:
    """Decision: stop the loop."""
    action: str = field(default="stop", init=False)
    diminishing_returns: bool = False
    duration_ms: float = 0
    pct: int = 0
    turn_tokens: int = 0
    budget: int = 0


BudgetDecision = BudgetContinue | BudgetStop


def create_budget_tracker(total_budget: int | None = None) -> BudgetTracker:
    """Create a new budget tracker."""
    return BudgetTracker(total_budget=total_budget)


def check_token_budget(
    tracker: BudgetTracker,
    turn_tokens: int,
) -> BudgetDecision:
    """Check if the query should continue or stop based on token budget.

    Parameters
    ----------
    tracker:
        The budget tracker with accumulated state.
    turn_tokens:
        Total tokens consumed in this turn so far.

    Returns
    -------
    BudgetContinue or BudgetStop decision.
    """
    budget = tracker.total_budget

    # No budget set — always continue
    if budget is None or budget <= 0:
        return BudgetStop(duration_ms=0, pct=0, turn_tokens=turn_tokens, budget=0)

    pct = round((turn_tokens / budget) * 100) if budget > 0 else 0

    # Check diminishing returns
    delta = turn_tokens - tracker.last_global_turn_tokens
    is_diminishing = (
        tracker.continuation_count >= MIN_CONTINUATIONS_FOR_DIMINISHING
        and delta < DIMINISHING_THRESHOLD
        and tracker.last_delta_tokens < DIMINISHING_THRESHOLD
    )

    # Update tracker
    tracker.last_delta_tokens = delta
    tracker.last_global_turn_tokens = turn_tokens

    # Under threshold and not diminishing — continue
    if turn_tokens < budget * COMPLETION_THRESHOLD and not is_diminishing:
        tracker.continuation_count += 1
        nudge = _build_nudge_message(pct, turn_tokens, budget)
        return BudgetContinue(
            nudge_message=nudge,
            pct=pct,
            turn_tokens=turn_tokens,
            budget=budget,
        )

    # Over threshold or diminishing — stop
    duration_ms = (time.time() - tracker.started_at) * 1000
    return BudgetStop(
        diminishing_returns=is_diminishing,
        duration_ms=duration_ms,
        pct=pct,
        turn_tokens=turn_tokens,
        budget=budget,
    )


def _build_nudge_message(pct: int, tokens: int, budget: int) -> str:
    """Build a nudge message for the model when continuing."""
    remaining = budget - tokens
    return (
        f"Token budget: {pct}% used ({tokens:,}/{budget:,} tokens). "
        f"{remaining:,} tokens remaining. Continue working efficiently."
    )
