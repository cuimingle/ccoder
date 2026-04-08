"""Claude Code theme — color palette matching the official Claude Code TUI."""
from __future__ import annotations

# ── Brand colors ──────────────────────────────────────────────────────
CLAUDE_ORANGE = "#d77757"  # rgb(215,119,87)
CLAUDE_ORANGE_SHIMMER = "#f59575"  # rgb(245,149,117)
CLAUDE_BLUE = "#5769f7"  # rgb(87,105,247)

# ── Semantic colors ───────────────────────────────────────────────────
SUCCESS = "#2c7a39"  # rgb(44,122,57)
ERROR = "#ab2b3f"  # rgb(171,43,63)
WARNING = "#966c1e"  # rgb(150,108,30)
INFO = CLAUDE_BLUE

# ── Text ──────────────────────────────────────────────────────────────
TEXT = "#e0e0e0"
TEXT_MUTED = "#888888"
TEXT_SUBTLE = "#666666"

# ── Surfaces ──────────────────────────────────────────────────────────
SURFACE = "#1a1a2e"
SURFACE_LIGHT = "#242440"
PANEL = "#16162a"
BACKGROUND = "#0f0f23"

# ── Diff colors ───────────────────────────────────────────────────────
DIFF_ADDED = "#69db7c"  # rgb(105,219,124)
DIFF_REMOVED = "#ffa8b4"  # rgb(255,168,180)

# ── Borders ───────────────────────────────────────────────────────────
BORDER_NORMAL = "#999999"
BORDER_FOCUSED = CLAUDE_ORANGE

# ── Permission ────────────────────────────────────────────────────────
PERMISSION = "#b1b9f9"  # rgb(177,185,249)

# ── Tool status indicators ────────────────────────────────────────────
TOOL_PENDING = "#966c1e"  # amber
TOOL_SUCCESS = SUCCESS
TOOL_ERROR = ERROR

# ── Spinner ───────────────────────────────────────────────────────────
SPINNER_COLOR = CLAUDE_ORANGE

# ── Textual CSS theme variables ───────────────────────────────────────
CLAUDE_DARK_CSS = """
$claude-orange: #d77757;
$claude-orange-light: #f59575;
$claude-blue: #5769f7;
$success-color: #2c7a39;
$error-color: #ab2b3f;
$warning-color: #966c1e;
$text-muted-color: #888888;
$surface-color: #1a1a2e;
$surface-light: #242440;
$panel-color: #16162a;
$bg-color: #0f0f23;
$border-color: #999999;
$permission-color: #b1b9f9;
$diff-added: #69db7c;
$diff-removed: #ffa8b4;
"""
