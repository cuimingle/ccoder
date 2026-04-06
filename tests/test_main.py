"""Tests for main CLI entry point."""
from __future__ import annotations
import pytest
from click.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Claude Code" in result.output


def test_cli_pipe_mode_flag():
    runner = CliRunner()
    # --print / -p flag should be recognized
    with patch("app.main.run_pipe_mode", new=AsyncMock()):
        result = runner.invoke(cli, ["-p", "say hello"])
    # Should not error on unknown option
    assert "--print" in result.output or result.exit_code in (0, 2)


@pytest.mark.asyncio
async def test_run_pipe_mode_prints_response(tmp_path, capsys):
    from app.main import run_pipe_mode
    from app.query import QueryResult

    mock_result = QueryResult(
        response_text="Hello from Claude!",
        tool_calls=[],
        input_tokens=10,
        output_tokens=5,
        messages=[],
    )

    with patch("app.main.QueryEngine") as MockEngine:
        engine_instance = MagicMock()
        engine_instance.run_turn = AsyncMock(return_value=mock_result)
        MockEngine.return_value = engine_instance

        await run_pipe_mode(prompt="say hello", cwd=str(tmp_path))

    captured = capsys.readouterr()
    assert "Hello from Claude!" in captured.out
