"""Messages widget — scrollable conversation display with markdown rendering and tool status."""
from __future__ import annotations

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static, Markdown

from app.themes.claude_theme import (
    CLAUDE_ORANGE,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    SUCCESS,
    ERROR,
    WARNING,
    TOOL_PENDING,
    TOOL_SUCCESS,
    TOOL_ERROR,
    DIFF_ADDED,
    DIFF_REMOVED,
    SURFACE_LIGHT,
)


class _UserMessage(Static):
    """A user message row with '>' prefix."""

    DEFAULT_CSS = """
    _UserMessage {
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """


class _AssistantMessage(Static):
    """A streaming assistant message rendered as markdown."""

    DEFAULT_CSS = """
    _AssistantMessage {
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """


class _ToolCallRow(Static):
    """A tool invocation indicator row."""

    DEFAULT_CSS = """
    _ToolCallRow {
        margin: 0 0 0 0;
        padding: 0 1;
    }
    """


class _ToolResultRow(Static):
    """A tool result display."""

    DEFAULT_CSS = """
    _ToolResultRow {
        margin: 0 0 1 0;
        padding: 0 1 0 3;
    }
    """


class _SystemMessage(Static):
    """A system notification message."""

    DEFAULT_CSS = """
    _SystemMessage {
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """


# ── Tool icons ────────────────────────────────────────────────────────
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

# ── Status symbols ────────────────────────────────────────────────────
_STATUS_PENDING = "⏺"
_STATUS_SUCCESS = "✔"
_STATUS_ERROR = "✘"


class Messages(VerticalScroll):
    """Displays conversation messages with markdown rendering and tool status."""

    DEFAULT_CSS = """
    Messages {
        height: 1fr;
        padding: 0 0;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._assistant_buffer: str = ""
        self._assistant_widget: _AssistantMessage | None = None
        self._streaming: bool = False
        self._tool_widgets: dict[str, _ToolCallRow] = {}
        self._tool_counter: int = 0

    # ── User messages ─────────────────────────────────────────────────

    def append_user(self, text: str) -> None:
        """Add a user message."""
        rendered = Text()
        rendered.append("❯ ", style=f"bold {CLAUDE_ORANGE}")
        rendered.append(text, style=f"{TEXT}")
        widget = _UserMessage(rendered)
        self.mount(widget)
        self.scroll_end(animate=False)

    # ── Assistant streaming ───────────────────────────────────────────

    def append_assistant_chunk(self, text: str) -> None:
        """Append streaming text to the current assistant message."""
        self._assistant_buffer += text
        if self._assistant_widget is None:
            self._assistant_widget = _AssistantMessage(self._assistant_buffer)
            self.mount(self._assistant_widget)
            self._streaming = True
        else:
            self._assistant_widget.update(self._assistant_buffer)
        self.scroll_end(animate=False)

    def finalize_assistant(self) -> None:
        """Mark current assistant message as complete, re-render as markdown."""
        if self._assistant_widget and self._assistant_buffer.strip():
            # Replace with a proper Markdown widget for final rendering
            md_widget = Markdown(
                self._assistant_buffer,
                classes="assistant-markdown",
            )
            self._assistant_widget.remove()
            self.mount(md_widget)
            self.scroll_end(animate=False)
        self._assistant_buffer = ""
        self._assistant_widget = None
        self._streaming = False

    # ── Tool calls ────────────────────────────────────────────────────

    def append_tool_call(self, name: str, tool_input: dict) -> None:
        """Show a tool invocation with icon and pending status."""
        if self._streaming:
            self.finalize_assistant()

        self._tool_counter += 1
        tool_id = f"tool-{self._tool_counter}"

        icon = _TOOL_ICONS.get(name, "⚙")
        summary = _format_tool_input(name, tool_input)

        rendered = Text()
        rendered.append(f"  {_STATUS_PENDING} ", style=f"bold {TOOL_PENDING}")
        rendered.append(f"{icon} ", style="")
        rendered.append(f"{name}", style=f"bold {TEXT}")
        rendered.append(f"  {summary}", style=f"{TEXT_MUTED}")

        widget = _ToolCallRow(rendered, id=tool_id)
        self._tool_widgets[name] = widget
        self.mount(widget)
        self.scroll_end(animate=False)

    def append_tool_result(
        self, name: str, content: str, is_error: bool = False
    ) -> None:
        """Show a tool execution result and update the tool call status."""
        # Update the tool call row status indicator
        if name in self._tool_widgets:
            old_widget = self._tool_widgets[name]
            icon = _TOOL_ICONS.get(name, "⚙")
            summary = _format_tool_input_from_widget(old_widget)

            rendered = Text()
            if is_error:
                rendered.append(f"  {_STATUS_ERROR} ", style=f"bold {TOOL_ERROR}")
            else:
                rendered.append(f"  {_STATUS_SUCCESS} ", style=f"bold {TOOL_SUCCESS}")
            rendered.append(f"{icon} ", style="")
            rendered.append(f"{name}", style=f"bold {TEXT}")
            rendered.append(f"  done", style=f"{TEXT_SUBTLE}")
            old_widget.update(rendered)
            del self._tool_widgets[name]

        # Show result content (truncated)
        display = content[:2000] + "…" if len(content) > 2000 else content
        if display.strip():
            rendered = Text()
            if is_error:
                rendered.append("  ✘ ", style=f"bold {ERROR}")
                rendered.append(display, style=f"{ERROR}")
            else:
                rendered.append(display, style=f"{TEXT_MUTED}")
            widget = _ToolResultRow(rendered)
            self.mount(widget)
        self.scroll_end(animate=False)

    # ── System messages ───────────────────────────────────────────────

    def append_system(self, text: str) -> None:
        """Add a system message (compact notification, cancel, etc.)."""
        rendered = Text()
        rendered.append(f"  ℹ {text}", style=f"italic {WARNING}")
        widget = _SystemMessage(rendered)
        self.mount(widget)
        self.scroll_end(animate=False)

    # ── Clear ─────────────────────────────────────────────────────────

    def clear_messages(self) -> None:
        """Remove all messages."""
        self.remove_children()
        self._assistant_buffer = ""
        self._assistant_widget = None
        self._streaming = False
        self._tool_widgets.clear()
        self._tool_counter = 0


def _format_tool_input(name: str, tool_input: dict) -> str:
    """Format tool input for brief display."""
    if name == "Bash":
        return tool_input.get("command", str(tool_input))[:120]
    if name in ("Read", "Edit", "Write", "FileRead", "FileEdit", "FileWrite"):
        return tool_input.get("file_path", str(tool_input))[:120]
    if name in ("Grep", "Glob"):
        return tool_input.get("pattern", str(tool_input))[:120]
    if name in ("WebSearch", "WebFetch"):
        return tool_input.get("query", tool_input.get("url", str(tool_input)))[:120]
    # Generic fallback
    parts = [f"{k}={v!r}" for k, v in list(tool_input.items())[:3]]
    return ", ".join(parts)[:120]


def _format_tool_input_from_widget(widget: _ToolCallRow) -> str:
    """Extract the summary text from an existing tool call widget."""
    # We stored the summary in the rendered text; just return empty since
    # we're replacing the whole line anyway
    return ""
