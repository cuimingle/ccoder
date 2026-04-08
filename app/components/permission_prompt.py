"""PermissionPrompt widget — styled permission dialog matching Claude Code TUI."""
from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static
from textual.widget import Widget

from app.themes.claude_theme import (
    CLAUDE_ORANGE,
    PERMISSION,
    TEXT,
    TEXT_MUTED,
    WARNING,
    SUCCESS,
    ERROR,
)
from app.types.permissions import PermissionResult

# Tool icons for permission display
_TOOL_ICONS = {
    "Bash": "⌘",
    "Read": "📄",
    "FileRead": "📄",
    "Edit": "✏️",
    "FileEdit": "✏️",
    "Write": "📝",
    "FileWrite": "📝",
    "Grep": "🔍",
    "Glob": "📂",
    "WebSearch": "🌐",
    "WebFetch": "🌐",
    "Agent": "🤖",
}


class PermissionPrompt(Widget):
    """Styled permission dialog shown when a tool needs user approval."""

    DEFAULT_CSS = """
    PermissionPrompt {
        height: auto;
        padding: 1 2;
        display: none;
    }
    PermissionPrompt.visible {
        display: block;
        background: #1a1a2e;
        border: heavy #b1b9f9;
        margin: 0 1 1 1;
    }
    PermissionPrompt .perm-header {
        margin-bottom: 1;
    }
    PermissionPrompt .perm-detail {
        margin-bottom: 1;
        padding: 0 1;
    }
    PermissionPrompt .perm-buttons {
        height: 3;
    }
    PermissionPrompt Button {
        margin-right: 1;
        min-width: 16;
    }
    """

    class Resolved(Message):
        """Posted when user makes a permission decision."""

        def __init__(self, result: PermissionResult) -> None:
            super().__init__()
            self.result = result

    def compose(self):
        yield Static("", id="perm-header", classes="perm-header")
        yield Static("", id="perm-detail", classes="perm-detail")
        yield Horizontal(
            Button("  Allow (y)  ", id="perm-allow", variant="success"),
            Button(" Always Allow ", id="perm-allow-always", variant="success"),
            Button("  Deny (n)   ", id="perm-deny", variant="error"),
            Button(" Always Deny  ", id="perm-deny-always", variant="error"),
            classes="perm-buttons",
        )

    def show_prompt(self, tool_name: str, tool_input: dict) -> None:
        """Show the permission prompt for a tool call."""
        icon = _TOOL_ICONS.get(tool_name, "⚙")

        # Header
        header_text = Text()
        header_text.append(f"  {icon} ", style="")
        header_text.append("Permission required: ", style=f"bold {PERMISSION}")
        header_text.append(f"{tool_name}", style=f"bold {TEXT}")
        self.query_one("#perm-header", Static).update(header_text)

        # Detail
        detail = _format_input(tool_name, tool_input)
        detail_text = Text()
        detail_text.append(detail, style=f"{TEXT_MUTED}")
        self.query_one("#perm-detail", Static).update(detail_text)

        self.add_class("visible")

    def hide_prompt(self) -> None:
        """Hide the permission prompt."""
        self.remove_class("visible")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        result_map = {
            "perm-allow": PermissionResult.ALLOW,
            "perm-allow-always": PermissionResult.ALLOW_ALWAYS,
            "perm-deny": PermissionResult.DENY,
            "perm-deny-always": PermissionResult.DENY_ALWAYS,
        }
        result = result_map.get(event.button.id)
        if result is not None:
            self.post_message(self.Resolved(result))

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts for permission decisions."""
        if not self.has_class("visible"):
            return
        if event.key == "y":
            self.post_message(self.Resolved(PermissionResult.ALLOW))
            event.prevent_default()
        elif event.key == "n":
            self.post_message(self.Resolved(PermissionResult.DENY))
            event.prevent_default()


def _format_input(tool_name: str, tool_input: dict) -> str:
    """Format tool input for the permission prompt display."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Command: {cmd}"
    if tool_name in ("Read", "Edit", "Write", "FileRead", "FileEdit", "FileWrite"):
        path = tool_input.get("file_path", "")
        return f"File: {path}"
    if tool_name in ("Grep", "Glob"):
        pattern = tool_input.get("pattern", "")
        return f"Pattern: {pattern}"
    # Generic
    parts = [f"{k}: {v!r}" for k, v in list(tool_input.items())[:5]]
    return "\n".join(parts)[:500]
