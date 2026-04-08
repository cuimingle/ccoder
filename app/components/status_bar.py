"""Status bar widget — footer pills showing model, permission mode, context usage, cost."""
from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from app.themes.claude_theme import (
    CLAUDE_ORANGE,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    SUCCESS,
    WARNING,
    PERMISSION,
    SURFACE_LIGHT,
)

# ── Permission mode icons ─────────────────────────────────────────────
_MODE_ICONS = {
    "plan": "👁",
    "auto": "⚡",
    "manual": "🛡",
}

_MODE_LABELS = {
    "plan": "Plan",
    "auto": "Auto",
    "manual": "Manual",
}


class StatusBar(Widget):
    """Footer status bar with pill-style indicators."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._model: str = ""
        self._permission_mode: str = "manual"
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._context_pct: float = 0.0
        self._cost: float = 0.0
        self._cwd: str = ""
        self._input_mode: str = "prompt"

    def update_state(
        self,
        model: str = "",
        permission_mode: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        context_pct: float = 0.0,
        cost: float = 0.0,
        cwd: str = "",
        input_mode: str = "prompt",
    ) -> None:
        """Update all status values and refresh."""
        if model:
            self._model = model
        if permission_mode:
            self._permission_mode = permission_mode
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._context_pct = context_pct
        self._cost = cost
        if cwd:
            self._cwd = cwd
        self._input_mode = input_mode
        self.refresh()

    def render(self) -> Text:
        output = Text()
        sep = Text(" │ ", style=f"{TEXT_SUBTLE}")

        # Permission mode pill
        icon = _MODE_ICONS.get(self._permission_mode, "🛡")
        label = _MODE_LABELS.get(self._permission_mode, self._permission_mode)
        output.append(f" {icon} {label} ", style=f"bold {PERMISSION}")

        output.append(sep)

        # Model pill
        if self._model:
            output.append(f"{self._model}", style=f"{CLAUDE_ORANGE}")
            output.append(sep)

        # Input mode (only show if BASH)
        if self._input_mode == "bash":
            output.append("BASH", style=f"bold reverse {WARNING}")
            output.append(sep)

        # Context usage
        if self._context_pct > 0:
            color = SUCCESS
            if self._context_pct > 70:
                color = WARNING
            if self._context_pct > 90:
                color = "#ab2b3f"
            output.append(f"ctx {self._context_pct:.0f}%", style=f"{color}")
            output.append(sep)

        # Token counts
        output.append(
            f"↑{self._input_tokens:,} ↓{self._output_tokens:,}",
            style=f"{TEXT_MUTED}",
        )

        # Cost
        if self._cost > 0:
            output.append(sep)
            output.append(f"${self._cost:.4f}", style=f"{TEXT_MUTED}")

        # CWD (right-aligned — just append, Textual handles overflow)
        if self._cwd:
            output.append(sep)
            # Shorten cwd: show last 2 path components
            parts = self._cwd.split("/")
            short_cwd = "/".join(parts[-2:]) if len(parts) > 2 else self._cwd
            output.append(f"{short_cwd}", style=f"{TEXT_SUBTLE}")

        return output
