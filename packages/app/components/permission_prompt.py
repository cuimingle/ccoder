"""PermissionPrompt widget — inline permission dialog for manual mode."""
from __future__ import annotations

from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static
from textual.widget import Widget

from app.types.permissions import PermissionResult


class PermissionPrompt(Widget):
    """Inline permission dialog shown when a tool needs user approval."""

    DEFAULT_CSS = """
    PermissionPrompt {
        height: auto;
        padding: 0 1;
        display: none;
    }
    PermissionPrompt.visible {
        display: block;
        background: $warning 20%;
        border: tall $warning;
        margin-bottom: 1;
    }
    PermissionPrompt .prompt-info {
        margin-bottom: 1;
    }
    PermissionPrompt Button {
        margin-right: 1;
    }
    """

    class Resolved(Message):
        """Posted when user makes a permission decision."""

        def __init__(self, result: PermissionResult) -> None:
            super().__init__()
            self.result = result

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._info_widget: Static | None = None
        self._buttons: Horizontal | None = None

    def compose(self):
        yield Static("", id="perm-info", classes="prompt-info")
        yield Horizontal(
            Button("Allow", id="perm-allow", variant="success"),
            Button("Always Allow", id="perm-allow-always", variant="success"),
            Button("Deny", id="perm-deny", variant="error"),
            Button("Always Deny", id="perm-deny-always", variant="error"),
        )

    def show_prompt(self, tool_name: str, tool_input: dict) -> None:
        """Show the permission prompt for a tool call."""
        summary = _format_input(tool_name, tool_input)
        info = self.query_one("#perm-info", Static)
        info.update(f"[bold]Permission required:[/bold] {tool_name}\n{summary}")
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


def _format_input(tool_name: str, tool_input: dict) -> str:
    """Format tool input for the permission prompt display."""
    if tool_name == "Bash":
        return f"Command: {tool_input.get('command', '')}"
    if tool_name in ("Read", "Edit", "Write", "FileRead", "FileEdit", "FileWrite"):
        return f"File: {tool_input.get('file_path', '')}"
    # Generic
    parts = [f"{k}: {v!r}" for k, v in list(tool_input.items())[:5]]
    return "\n".join(parts)[:500]
