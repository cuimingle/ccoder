"""Module-level singletons for session-global state."""
from __future__ import annotations
import os
import uuid
from pathlib import Path


# Session ID — generated once per process
_session_id: str = str(uuid.uuid4())

# Working directory at startup
_original_cwd: Path = Path(os.getcwd())

# Token counts for the session
_session_input_tokens: int = 0
_session_output_tokens: int = 0


def get_session_id() -> str:
    return _session_id


def get_original_cwd() -> Path:
    return _original_cwd


def get_session_tokens() -> tuple[int, int]:
    """Returns (input_tokens, output_tokens)."""
    return _session_input_tokens, _session_output_tokens


def add_tokens(input_tokens: int, output_tokens: int) -> None:
    global _session_input_tokens, _session_output_tokens
    _session_input_tokens += input_tokens
    _session_output_tokens += output_tokens
