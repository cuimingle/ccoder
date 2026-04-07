"""Tests for direct bash command execution."""
import pytest

from app.commands.bash_exec import execute_bash


@pytest.mark.asyncio
async def test_echo_command(tmp_path):
    result = await execute_bash("echo hello", str(tmp_path))
    assert "hello" in result.text
    assert result.handled is True


@pytest.mark.asyncio
async def test_empty_command(tmp_path):
    result = await execute_bash("", str(tmp_path))
    assert "No command" in result.text


@pytest.mark.asyncio
async def test_nonzero_exit(tmp_path):
    result = await execute_bash("false", str(tmp_path))
    assert "Exit code" in result.text


@pytest.mark.asyncio
async def test_stderr_output(tmp_path):
    result = await execute_bash("echo err >&2", str(tmp_path))
    assert "err" in result.text


@pytest.mark.asyncio
async def test_cwd_respected(tmp_path):
    result = await execute_bash("pwd", str(tmp_path))
    assert str(tmp_path) in result.text
