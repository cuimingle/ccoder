"""Feature flags — simple env-var-based feature gating.

Replaces TypeScript's Statsig/GrowthBook integration with a lightweight
env-var check pattern.
"""
from __future__ import annotations

import os

_TRUTHY = frozenset(("1", "true", "yes"))


def is_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled via environment variable.

    Looks for ``CLAUDE_CODE_{flag}`` in the environment.
    """
    return os.environ.get(f"CLAUDE_CODE_{flag}", "").lower() in _TRUTHY


# Convenience predicates for commonly-checked flags

def streaming_tool_execution_enabled() -> bool:
    """Whether tools should start executing during model streaming."""
    # Default to True — the TypeScript reference enables this by default
    val = os.environ.get("CLAUDE_CODE_STREAMING_TOOL_EXECUTION", "1")
    return val.lower() in _TRUTHY


def emit_tool_use_summaries() -> bool:
    return is_enabled("EMIT_TOOL_USE_SUMMARIES")
