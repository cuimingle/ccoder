"""Integration tests for the REPL screen."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.query import QueryResult
from app.query_engine import QueryEngine
from app.screens.repl import ClaudeCodeApp
from app.state.app_state import AppState
from app.tool import ToolResult
from app.components.messages import Messages
from app.components.prompt_input import PromptInput


def _make_app(query_result=None):
    """Create a ClaudeCodeApp with a mocked QueryEngine."""
    engine = MagicMock(spec=QueryEngine)
    engine.turn_count = 1
    engine.total_input_tokens = 100
    engine.total_output_tokens = 50
    engine.clear = MagicMock()

    if query_result is None:
        query_result = QueryResult(
            response_text="Hello from Claude!",
            tool_calls=[],
            input_tokens=100,
            output_tokens=50,
        )
    engine.run_turn = AsyncMock(return_value=query_result)

    state = AppState(cwd="/tmp/test", model="test-model")
    app = ClaudeCodeApp(engine=engine, state=state)
    return app


class TestREPLApp:
    @pytest.mark.asyncio
    async def test_app_composes_widgets(self):
        app = _make_app()
        async with app.run_test() as pilot:
            assert app.query_one("#messages", Messages) is not None
            assert app.query_one("#input", PromptInput) is not None

    @pytest.mark.asyncio
    async def test_input_focused_on_mount(self):
        app = _make_app()
        async with app.run_test() as pilot:
            assert app.focused is app.query_one("#input", PromptInput)

    @pytest.mark.asyncio
    async def test_clear_screen_action(self):
        app = _make_app()
        async with app.run_test() as pilot:
            messages = app.query_one("#messages", Messages)
            messages.append_user("test")
            await pilot.pause()
            app.action_clear_screen()
            await pilot.pause()
            assert len(messages.children) == 0
            app.engine.clear.assert_called_once()
