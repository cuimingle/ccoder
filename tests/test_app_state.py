"""Tests for AppState dataclass."""
from app.state.app_state import AppState


class TestAppState:
    def test_defaults(self):
        state = AppState(cwd="/tmp", model="claude-opus-4-6")
        assert state.cwd == "/tmp"
        assert state.model == "claude-opus-4-6"
        assert state.permission_mode == "manual"
        assert state.is_busy is False
        assert state.input_history == []
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0
        assert state.turn_count == 0

    def test_custom_values(self):
        state = AppState(
            cwd="/home",
            model="test-model",
            permission_mode="auto",
            is_busy=True,
            turn_count=5,
        )
        assert state.permission_mode == "auto"
        assert state.is_busy is True
        assert state.turn_count == 5

    def test_input_history_mutable(self):
        state = AppState(cwd="/tmp", model="m")
        state.input_history.append("hello")
        assert len(state.input_history) == 1
        assert state.input_history[0] == "hello"
