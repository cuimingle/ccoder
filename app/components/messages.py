"""Messages widget — scrollable conversation display with streaming support."""
from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class Messages(VerticalScroll):
    """Displays conversation messages with streaming assistant text."""

    DEFAULT_CSS = """
    Messages {
        height: 1fr;
        padding: 0 1;
    }
    Messages .user-message {
        color: $text;
        margin-bottom: 1;
    }
    Messages .assistant-message {
        color: $success;
        margin-bottom: 1;
    }
    Messages .tool-call {
        color: $text-muted;
        margin-bottom: 0;
    }
    Messages .tool-result {
        color: $text-muted;
        margin-bottom: 1;
    }
    Messages .tool-error {
        color: $error;
        margin-bottom: 1;
    }
    Messages .system-message {
        color: $warning;
        text-style: italic;
        margin-bottom: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._assistant_buffer: str = ""
        self._assistant_widget: Static | None = None
        self._streaming: bool = False

    def append_user(self, text: str) -> None:
        """Add a user message."""
        widget = Static(f"> {text}", classes="user-message")
        self.mount(widget)
        self.scroll_end(animate=False)

    def append_assistant_chunk(self, text: str) -> None:
        """Append streaming text to the current assistant message."""
        self._assistant_buffer += text
        if self._assistant_widget is None:
            self._assistant_widget = Static(
                self._assistant_buffer, classes="assistant-message"
            )
            self.mount(self._assistant_widget)
            self._streaming = True
        else:
            self._assistant_widget.update(self._assistant_buffer)
        self.scroll_end(animate=False)

    def finalize_assistant(self) -> None:
        """Mark current assistant message as complete."""
        self._assistant_buffer = ""
        self._assistant_widget = None
        self._streaming = False

    def append_tool_call(self, name: str, tool_input: dict) -> None:
        """Show a tool invocation."""
        # Finalize any in-progress assistant text first
        if self._streaming:
            self.finalize_assistant()

        summary = _format_tool_input(name, tool_input)
        widget = Static(f"[bold]Tool:[/bold] {name} — {summary}", classes="tool-call")
        self.mount(widget)
        self.scroll_end(animate=False)

    def append_tool_result(
        self, name: str, content: str, is_error: bool = False
    ) -> None:
        """Show a tool execution result."""
        # Truncate very long results for display
        display = content[:2000] + "..." if len(content) > 2000 else content
        css_class = "tool-error" if is_error else "tool-result"
        prefix = "[red]Error:[/red]" if is_error else "Result:"
        widget = Static(f"  {prefix} {display}", classes=css_class)
        self.mount(widget)
        self.scroll_end(animate=False)

    def append_system(self, text: str) -> None:
        """Add a system message (compact notification, cancel, etc.)."""
        widget = Static(f"[italic]{text}[/italic]", classes="system-message")
        self.mount(widget)
        self.scroll_end(animate=False)

    def clear_messages(self) -> None:
        """Remove all messages."""
        self.remove_children()
        self._assistant_buffer = ""
        self._assistant_widget = None
        self._streaming = False


def _format_tool_input(name: str, tool_input: dict) -> str:
    """Format tool input for brief display."""
    if name == "Bash":
        return tool_input.get("command", str(tool_input))[:200]
    if name in ("Read", "Edit", "Write", "FileRead", "FileEdit", "FileWrite"):
        return tool_input.get("file_path", str(tool_input))[:200]
    if name in ("Grep", "Glob"):
        return tool_input.get("pattern", str(tool_input))[:200]
    # Generic fallback
    parts = [f"{k}={v!r}" for k, v in list(tool_input.items())[:3]]
    return ", ".join(parts)[:200]
