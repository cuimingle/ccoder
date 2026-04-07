"""Central application state for the TUI session."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppState:
    """UI-relevant state for the REPL session.

    Note: QueryEngine tracks messages and detailed token counts separately.
    AppState holds only what the TUI needs for display and interaction.
    """

    cwd: str
    model: str
    permission_mode: str = "manual"
    is_busy: bool = False
    input_history: list[str] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    turn_count: int = 0
    session_name: str = ""
    extra_dirs: list[str] = field(default_factory=list)
