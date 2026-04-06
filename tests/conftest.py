"""Shared pytest fixtures."""
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    (tmp_path / "CLAUDE.md").write_text("# Test Project\n")
    return tmp_path


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for tests."""
    client = MagicMock()
    client.messages = MagicMock()
    return client
