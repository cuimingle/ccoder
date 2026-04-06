"""Tests for message type hierarchy."""
from __future__ import annotations
import pytest
from app.types.message import (
    UserMessage,
    AssistantMessage,
    ToolUseBlock,
    ToolResultBlock,
    TextBlock,
    SystemMessage,
    MessageRole,
)
from app.types.permissions import PermissionMode


def test_user_message_creation():
    msg = UserMessage(content="hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "hello"


def test_assistant_message_with_text_block():
    block = TextBlock(text="Hello!")
    msg = AssistantMessage(content=[block])
    assert msg.role == MessageRole.ASSISTANT
    assert len(msg.content) == 1
    assert msg.content[0].text == "Hello!"


def test_tool_use_block():
    block = ToolUseBlock(id="call_123", name="BashTool", input={"command": "ls"})
    assert block.type == "tool_use"
    assert block.name == "BashTool"
    assert block.input == {"command": "ls"}


def test_tool_result_block():
    block = ToolResultBlock(tool_use_id="call_123", content="file1.py\nfile2.py")
    assert block.type == "tool_result"
    assert block.tool_use_id == "call_123"


def test_permission_mode_enum():
    assert PermissionMode.MANUAL.value == "manual"
    assert PermissionMode.AUTO.value == "auto"
    assert PermissionMode.PLAN.value == "plan"
