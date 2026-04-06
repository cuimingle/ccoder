"""Tests for Task management tools."""
from __future__ import annotations
import json
import re
import pytest
from app.tools.task_tool import TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool, _task_stores
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    session_id = "test-session-" + str(id(tmp_path))
    # Clear any existing tasks for this session to ensure test isolation
    if session_id in _task_stores:
        _task_stores[session_id].clear()
    return ToolContext(cwd=str(tmp_path), session_id=session_id)

@pytest.mark.asyncio
async def test_task_create(ctx):
    result = await TaskCreateTool().call({
        "subject": "Test task",
        "description": "Do something",
    }, ctx)
    assert result.is_error is False
    assert "created" in result.content.lower() or "task" in result.content.lower()

@pytest.mark.asyncio
async def test_task_list_empty(ctx):
    result = await TaskListTool().call({}, ctx)
    assert result.is_error is False

@pytest.mark.asyncio
async def test_task_create_and_list(ctx):
    await TaskCreateTool().call({
        "subject": "My task",
        "description": "Details here",
    }, ctx)

    list_result = await TaskListTool().call({}, ctx)
    assert "My task" in list_result.content

@pytest.mark.asyncio
async def test_task_update_status(ctx):
    await TaskCreateTool().call({"subject": "Update me", "description": "desc"}, ctx)
    list_result = await TaskListTool().call({}, ctx)
    match = re.search(r"#(\d+)", list_result.content)
    assert match, f"No task ID found in: {list_result.content}"
    task_id = match.group(1)
    update_result = await TaskUpdateTool().call({"taskId": task_id, "status": "in_progress"}, ctx)
    assert update_result.is_error is False

@pytest.mark.asyncio
async def test_task_get_returns_details(ctx):
    await TaskCreateTool().call({"subject": "Get me", "description": "my description"}, ctx)
    list_result = await TaskListTool().call({}, ctx)
    match = re.search(r"#(\d+)", list_result.content)
    task_id = match.group(1)
    get_result = await TaskGetTool().call({"taskId": task_id}, ctx)
    assert get_result.is_error is False
    data = json.loads(get_result.content)
    assert data["subject"] == "Get me"
    assert data["description"] == "my description"

@pytest.mark.asyncio
async def test_task_get_not_found(ctx):
    result = await TaskGetTool().call({"taskId": "9999"}, ctx)
    assert result.is_error is True

@pytest.mark.asyncio
async def test_task_deletion(ctx):
    """Test that deleted tasks don't appear in list but return error on get."""
    # Create a task
    await TaskCreateTool().call({"subject": "Delete me", "description": "desc"}, ctx)
    list_result = await TaskListTool().call({}, ctx)
    match = re.search(r"#(\d+)", list_result.content)
    task_id = match.group(1)

    # Delete the task
    delete_result = await TaskUpdateTool().call({"taskId": task_id, "status": "deleted"}, ctx)
    assert delete_result.is_error is False

    # Verify it doesn't appear in list
    list_result = await TaskListTool().call({}, ctx)
    assert "Delete me" not in list_result.content

    # Verify get returns error
    get_result = await TaskGetTool().call({"taskId": task_id}, ctx)
    assert get_result.is_error is True
    assert "deleted" in get_result.content.lower()

@pytest.mark.asyncio
async def test_session_isolation(tmp_path):
    """Test that tasks in one session don't appear in another session."""
    ctx1 = ToolContext(cwd=str(tmp_path), session_id="session-1")
    ctx2 = ToolContext(cwd=str(tmp_path), session_id="session-2")

    # Create task in session 1
    await TaskCreateTool().call({"subject": "Session 1 task", "description": "desc"}, ctx1)

    # Verify it appears in session 1
    list1 = await TaskListTool().call({}, ctx1)
    assert "Session 1 task" in list1.content

    # Verify it doesn't appear in session 2
    list2 = await TaskListTool().call({}, ctx2)
    assert "Session 1 task" not in list2.content
