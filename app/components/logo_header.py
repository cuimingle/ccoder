"""Logo header widget — Clawd mascot + Claude Code branding."""
from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from app.themes.claude_theme import CLAUDE_ORANGE, TEXT_MUTED, TEXT

# ── Clawd mascot (9 cols × 3 rows, block-drawing characters) ─────────
CLAWD_LINES = [
    " ▐▛███▜▌ ",
    "▝▜█████▛▘",
    "  ▘▘ ▝▝  ",
]


class LogoHeader(Widget):
    """Displays the Clawd mascot and Claude Code branding info."""

    DEFAULT_CSS = """
    LogoHeader {
        height: auto;
        padding: 1 2;
        margin-bottom: 0;
    }
    """

    def __init__(
        self,
        version: str = "0.1.0",
        model: str = "",
        cwd: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._version = version
        self._model = model
        self._cwd = cwd

    def render(self) -> Text:
        output = Text()

        # Clawd character + title on the same first line
        clawd_width = 10  # each CLAWD line is 10 chars

        # Line 1: clawd row 0 + "  Claude Code v{version}"
        line1 = Text(CLAWD_LINES[0], style=f"bold {CLAUDE_ORANGE}")
        line1.append("  Claude Code", style=f"bold {TEXT}")
        line1.append(f" v{self._version}", style=f"{TEXT_MUTED}")
        output.append(line1)
        output.append("\n")

        # Line 2: clawd row 1 + model info
        line2 = Text(CLAWD_LINES[1], style=f"bold {CLAUDE_ORANGE}")
        if self._model:
            line2.append(f"  {self._model}", style=f"{TEXT_MUTED}")
        output.append(line2)
        output.append("\n")

        # Line 3: clawd row 2 + cwd
        line3 = Text(CLAWD_LINES[2], style=f"bold {CLAUDE_ORANGE}")
        if self._cwd:
            line3.append(f"  {self._cwd}", style=f"{TEXT_MUTED}")
        output.append(line3)

        return output

    def update_info(self, model: str = "", cwd: str = "") -> None:
        """Update displayed model/cwd and refresh."""
        if model:
            self._model = model
        if cwd:
            self._cwd = cwd
        self.refresh()
