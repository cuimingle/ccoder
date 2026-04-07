"""Input mode system — detect and manage prompt vs bash input modes."""
from __future__ import annotations

from enum import Enum


class InputMode(Enum):
    """Input mode for the prompt."""

    PROMPT = "prompt"
    BASH = "bash"


def detect_mode(text: str) -> InputMode:
    """Detect input mode from text prefix. '!' means bash mode."""
    if text.strip().startswith("!"):
        return InputMode.BASH
    return InputMode.PROMPT


def strip_mode_prefix(text: str, mode: InputMode) -> str:
    """Remove the mode prefix character from input text."""
    if mode == InputMode.BASH:
        stripped = text.strip()
        if stripped.startswith("!"):
            return stripped[1:].strip()
    return text


def prepend_mode_prefix(text: str, mode: InputMode) -> str:
    """Add the mode prefix character to input text."""
    if mode == InputMode.BASH:
        stripped = text.lstrip("!")
        return f"!{stripped}"
    return text.lstrip("!")


def is_mode_character(text: str) -> bool:
    """Check if input is just the mode character alone."""
    return text.strip() == "!"
