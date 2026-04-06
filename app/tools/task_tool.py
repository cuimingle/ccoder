"""Task management tools — create, update, list, get, stop, output."""
from __future__ import annotations
import json
from app.tool import BaseTool, ToolContext, ToolResult

# In-memory task store keyed by session_id
_task_stores: dict[str, list[dict]] = {}


def _get_store(session_id: str) -> list[dict]:
    if session_id not in _task_stores:
        _task_stores[session_id] = []
    return _task_stores[session_id]


def _next_id(store: list[dict]) -> str:
    if not store:
        return "1"
    return str(max(int(t["id"]) for t in store) + 1)


# ──────────────────────────────────────────────────────────────────────
# TaskCreate
# ──────────────────────────────────────────────────────────────────────

_TASK_CREATE_PROMPT = """\
Use this tool to create a structured task list for your current coding session. \
This helps you track progress, organize complex tasks, and demonstrate thoroughness \
to the user.
It also helps the user understand the progress of the task and overall progress of \
their requests.

## When to Use This Tool

Use this tool proactively in these scenarios:

- Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
- Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
- Plan mode - When using plan mode, create a task list to track the work
- User explicitly requests todo list - When the user directly asks you to use the todo list
- User provides multiple tasks - When users provide a list of things to be done \
(numbered or comma-separated)
- After receiving new instructions - Immediately capture user requirements as tasks
- When you start working on a task - Mark it as in_progress BEFORE beginning work
- After completing a task - Mark it as completed and add any new follow-up tasks \
discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
- There is only a single, straightforward task
- The task is trivial and tracking it provides no organizational benefit
- The task can be completed in less than 3 trivial steps
- The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this \
case you are better off just doing the task directly.

## Task Fields

- **subject**: A brief, actionable title in imperative form \
(e.g., "Fix authentication bug in login flow")
- **description**: What needs to be done
- **activeForm** (optional): Present continuous form shown in the spinner when the task \
is in_progress (e.g., "Fixing authentication bug"). If omitted, the spinner shows the \
subject instead.

All tasks are created with status `pending`.

## Tips

- Create tasks with clear, specific subjects that describe the outcome
- After creating tasks, use TaskUpdate to set up dependencies (blocks/blockedBy) if needed
- Check TaskList first to avoid creating duplicate tasks\
"""


class TaskCreateTool(BaseTool):
    name = "TaskCreate"

    input_schema = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "A brief title for the task",
            },
            "description": {
                "type": "string",
                "description": "What needs to be done",
            },
            "activeForm": {
                "type": "string",
                "description": (
                    "Present continuous form shown in spinner when in_progress "
                    '(e.g., "Running tests")'
                ),
            },
            "metadata": {
                "type": "object",
                "description": "Arbitrary metadata to attach to the task",
            },
        },
        "required": ["subject", "description"],
    }

    async def prompt(self) -> str:
        return _TASK_CREATE_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task = {
            "id": _next_id(store),
            "subject": input_data["subject"],
            "description": input_data["description"],
            "status": "pending",
            "owner": "",
            "activeForm": input_data.get("activeForm", ""),
            "blocks": [],
            "blockedBy": [],
            "metadata": input_data.get("metadata", {}),
        }
        store.append(task)
        return ToolResult(
            content=f"Task #{task['id']} created successfully: {task['subject']}"
        )


# ─────��──────────────────────────────��─────────────────────────────────
# TaskUpdate
# ───────��─────────────────────────────��────────────────────────────────

_TASK_UPDATE_PROMPT = """\
Use this tool to update a task in the task list.

## When to Use This Tool

**Mark tasks as resolved:**
- When you have completed the work described in a task
- When a task is no longer needed or has been superseded
- IMPORTANT: Always mark your assigned tasks as resolved when you finish them
- After resolving, call TaskList to find your next task

- ONLY mark a task as completed when you have FULLY accomplished it
- If you encounter errors, blockers, or cannot finish, keep the task as in_progress
- When blocked, create a new task describing what needs to be resolved
- Never mark a task as completed if:
  - Tests are failing
  - Implementation is partial
  - You encountered unresolved errors
  - You couldn't find necessary files or dependencies

**Delete tasks:**
- When a task is no longer relevant or was created in error
- Setting status to `deleted` permanently removes the task

**Update task details:**
- When requirements change or become clearer
- When establishing dependencies between tasks

## Fields You Can Update

- **status**: The task status (see Status Workflow below)
- **subject**: Change the task title (imperative form, e.g., "Run tests")
- **description**: Change the task description
- **activeForm**: Present continuous form shown in spinner when in_progress \
(e.g., "Running tests")
- **owner**: Change the task owner (agent name)
- **metadata**: Merge metadata keys into the task (set a key to null to delete it)
- **addBlocks**: Mark tasks that cannot start until this one completes
- **addBlockedBy**: Mark tasks that must complete before this one can start

## Status Workflow

Status progresses: `pending` \u2192 `in_progress` \u2192 `completed`

Use `deleted` to permanently remove a task.

## Staleness

Make sure to read a task's latest state using `TaskGet` before updating it.

## Examples

Mark task as in progress when starting work:
```json
{"taskId": "1", "status": "in_progress"}
```

Mark task as completed after finishing work:
```json
{"taskId": "1", "status": "completed"}
```

Delete a task:
```json
{"taskId": "1", "status": "deleted"}
```

Set up task dependencies:
```json
{"taskId": "2", "addBlockedBy": ["1"]}
```\
"""


class TaskUpdateTool(BaseTool):
    name = "TaskUpdate"

    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {
                "type": "string",
                "description": "The ID of the task to update",
            },
            "subject": {
                "type": "string",
                "description": "New subject for the task",
            },
            "description": {
                "type": "string",
                "description": "New description for the task",
            },
            "activeForm": {
                "type": "string",
                "description": (
                    "Present continuous form shown in spinner when in_progress "
                    '(e.g., "Running tests")'
                ),
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "deleted"],
                "description": "New status for the task",
            },
            "addBlocks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task IDs that this task blocks",
            },
            "addBlockedBy": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task IDs that block this task",
            },
            "owner": {
                "type": "string",
                "description": "New owner for the task",
            },
            "metadata": {
                "type": "object",
                "description": (
                    "Metadata keys to merge into the task. "
                    "Set a key to null to delete it."
                ),
            },
        },
        "required": ["taskId"],
    }

    async def prompt(self) -> str:
        return _TASK_UPDATE_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task_id = input_data["taskId"]
        task = next((t for t in store if t["id"] == task_id), None)
        if task is None:
            return ToolResult(content=f"Task #{task_id} not found", is_error=True)

        updated_fields = []

        if "status" in input_data:
            task["status"] = input_data["status"]
            updated_fields.append("status")
            if input_data["status"] == "deleted":
                return ToolResult(content=f"Task #{task_id} deleted")

        if "subject" in input_data:
            task["subject"] = input_data["subject"]
            updated_fields.append("subject")
        if "description" in input_data:
            task["description"] = input_data["description"]
            updated_fields.append("description")
        if "activeForm" in input_data:
            task["activeForm"] = input_data["activeForm"]
            updated_fields.append("activeForm")
        if "owner" in input_data:
            task["owner"] = input_data["owner"]
            updated_fields.append("owner")

        # Handle dependency additions
        if "addBlocks" in input_data:
            blocks = task.setdefault("blocks", [])
            for tid in input_data["addBlocks"]:
                if tid not in blocks:
                    blocks.append(tid)
            updated_fields.append("blocks")
        if "addBlockedBy" in input_data:
            blocked_by = task.setdefault("blockedBy", [])
            for tid in input_data["addBlockedBy"]:
                if tid not in blocked_by:
                    blocked_by.append(tid)
            updated_fields.append("blockedBy")

        # Merge metadata
        if "metadata" in input_data:
            meta = task.setdefault("metadata", {})
            for k, v in input_data["metadata"].items():
                if v is None:
                    meta.pop(k, None)
                else:
                    meta[k] = v
            updated_fields.append("metadata")

        fields_str = ", ".join(updated_fields) if updated_fields else "no fields"
        return ToolResult(content=f"Updated task #{task_id} ({fields_str})")


# ──���───────────────────────────────────────────────────────��───────────
# TaskList
# ──────────────────────────────────────────────────────────────────────

_TASK_LIST_PROMPT = """\
Use this tool to list all tasks in the task list.

## When to Use This Tool

- To see what tasks are available to work on (status: 'pending', no owner, not blocked)
- To check overall progress on the project
- To find tasks that are blocked and need dependencies resolved
- After completing a task, to check for newly unblocked work or claim the next available task
- **Prefer working on tasks in ID order** (lowest ID first) when multiple tasks are \
available, as earlier tasks often set up context for later ones

## Output

Returns a summary of each task:
- **id**: Task identifier (use with TaskGet, TaskUpdate)
- **subject**: Brief description of the task
- **status**: 'pending', 'in_progress', or 'completed'
- **owner**: Agent ID if assigned, empty if available
- **blockedBy**: List of open task IDs that must be resolved first (tasks with blockedBy \
cannot be claimed until dependencies resolve)

Use TaskGet with a specific task ID to view full details including description and comments.\
"""


class TaskListTool(BaseTool):
    name = "TaskList"

    input_schema = {"type": "object", "properties": {}}

    async def prompt(self) -> str:
        return _TASK_LIST_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        active = [t for t in store if t["status"] != "deleted"]
        if not active:
            return ToolResult(content="No tasks.")
        lines = []
        for t in active:
            blocked = t.get("blockedBy", [])
            # Filter out completed/deleted blockers
            open_blockers = [
                bid
                for bid in blocked
                if any(
                    bt["id"] == bid and bt["status"] not in ("completed", "deleted")
                    for bt in store
                )
            ]
            owner_str = f" owner={t['owner']}" if t.get("owner") else ""
            blocked_str = f" blockedBy=[{','.join(open_blockers)}]" if open_blockers else ""
            lines.append(
                f"#{t['id']}. [{t['status']}] {t['subject']}{owner_str}{blocked_str}"
            )
        return ToolResult(content="\n".join(lines))


# ───────────────────────────────────────────────────────���──────────────
# TaskGet
# ��─────────────────────────────────────────────────���───────────────────

_TASK_GET_PROMPT = """\
Use this tool to retrieve a task by its ID from the task list.

## When to Use This Tool

- When you need the full description and context before starting work on a task
- To understand task dependencies (what it blocks, what blocks it)
- After being assigned a task, to get complete requirements

## Output

Returns full task details:
- **subject**: Task title
- **description**: Detailed requirements and context
- **status**: 'pending', 'in_progress', or 'completed'
- **blocks**: Tasks waiting on this one to complete
- **blockedBy**: Tasks that must complete before this one can start

## Tips

- After fetching a task, verify its blockedBy list is empty before beginning work.
- Use TaskList to see all tasks in summary form.\
"""


class TaskGetTool(BaseTool):
    name = "TaskGet"

    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {
                "type": "string",
                "description": "The ID of the task to retrieve",
            },
        },
        "required": ["taskId"],
    }

    async def prompt(self) -> str:
        return _TASK_GET_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task = next((t for t in store if t["id"] == input_data["taskId"]), None)
        if task is None:
            return ToolResult(
                content=f"Task #{input_data['taskId']} not found", is_error=True
            )
        if task.get("status") == "deleted":
            return ToolResult(
                content=f"Task #{input_data['taskId']} has been deleted",
                is_error=True,
            )
        return ToolResult(content=json.dumps(task, ensure_ascii=False, indent=2))


# ───────��──────────────────────────────────────────────────────────────
# TaskStop
# ──���──────────────────────���────────────────────────────────────────────

_TASK_STOP_PROMPT = """\

- Stops a running background task by its ID
- Takes a task_id parameter identifying the task to stop
- Returns a success or failure status
- Use this tool when you need to terminate a long-running task\
"""


class TaskStopTool(BaseTool):
    name = "TaskStop"
    search_hint = "stop cancel running background task"

    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {
                "type": "string",
                "description": "The ID of the task to stop",
            },
        },
        "required": ["taskId"],
    }

    async def prompt(self) -> str:
        return _TASK_STOP_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task_id = input_data["taskId"]
        task = next((t for t in store if t["id"] == task_id), None)
        if task is None:
            return ToolResult(content=f"Task #{task_id} not found", is_error=True)
        if task["status"] not in ("pending", "in_progress"):
            return ToolResult(
                content=f"Task #{task_id} is already {task['status']}", is_error=True
            )
        task["status"] = "completed"
        return ToolResult(content=f"Task #{task_id} stopped successfully")


# ───────────────────��──────────────────────────────────────────────────
# TaskOutput
# ───────────────────���───────────────────────────────��──────────────────

_TASK_OUTPUT_PROMPT = """\
Retrieve the output or transcript of a background task by its ID. Use this to check \
what a background agent has produced so far.\
"""


class TaskOutputTool(BaseTool):
    name = "TaskOutput"
    search_hint = "get output transcript background task"

    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {
                "type": "string",
                "description": "The ID of the task to get output for",
            },
        },
        "required": ["taskId"],
    }

    async def prompt(self) -> str:
        return _TASK_OUTPUT_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task_id = input_data["taskId"]
        task = next((t for t in store if t["id"] == task_id), None)
        if task is None:
            return ToolResult(content=f"Task #{task_id} not found", is_error=True)
        output = task.get("output", "")
        if not output:
            return ToolResult(content=f"No output available for task #{task_id}")
        return ToolResult(content=output)
