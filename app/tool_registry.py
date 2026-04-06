"""Tool registry — assembles and filters the tool pool."""
from __future__ import annotations
from app.tool import find_tool_by_name


def get_all_base_tools() -> list:
    """Complete exhaustive list of all tool instances."""
    from app.tools.bash_tool import BashTool
    from app.tools.file_read_tool import FileReadTool
    from app.tools.file_edit_tool import FileEditTool
    from app.tools.file_write_tool import FileWriteTool
    from app.tools.grep_tool import GrepTool
    from app.tools.glob_tool import GlobTool
    from app.tools.web_fetch_tool import WebFetchTool
    from app.tools.web_search_tool import WebSearchTool
    from app.tools.ask_user_tool import AskUserQuestionTool
    from app.tools.agent_tool import AgentTool
    from app.tools.notebook_edit_tool import NotebookEditTool
    from app.tools.task_tool import (
        TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool,
        TaskStopTool, TaskOutputTool,
    )
    from app.tools.skill_tool import SkillTool
    from app.tools.plan_mode_tool import EnterPlanModeTool, ExitPlanModeTool
    from app.tools.tool_search_tool import ToolSearchTool
    from app.tools.worktree_tool import EnterWorktreeTool, ExitWorktreeTool
    from app.tools.cron_tool import CronCreateTool, CronListTool, CronDeleteTool
    from app.tools.send_message_tool import SendMessageTool

    return [
        # Core tools (always loaded)
        AgentTool(),
        AskUserQuestionTool(),
        BashTool(),
        FileEditTool(),
        FileReadTool(),
        FileWriteTool(),
        GlobTool(),
        GrepTool(),
        NotebookEditTool(),
        WebFetchTool(),
        WebSearchTool(),
        # Task tools
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskOutputTool(),
        TaskStopTool(),
        TaskUpdateTool(),
        # Planning tools
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        # Skill & search
        SkillTool(),
        ToolSearchTool(),
        # Worktree
        EnterWorktreeTool(),
        ExitWorktreeTool(),
        # Cron scheduling
        CronCreateTool(),
        CronDeleteTool(),
        CronListTool(),
        # Multi-agent
        SendMessageTool(),
    ]


def get_tools(permission_context: dict | None = None) -> list:
    """Return filtered, enabled tools for current context.

    Mirrors TS getTools(permissionContext): filters by isEnabled(),
    deny rules, and sorts by name for prompt-cache stability.
    """
    all_tools = get_all_base_tools()
    tools = [t for t in all_tools if t.is_enabled()]

    # Filter by deny rules if permission_context provided
    if permission_context:
        deny_rules = permission_context.get("deny_rules", [])
        if deny_rules:
            tools = filter_tools_by_deny_rules(tools, deny_rules)

    # Sort by name for prompt-cache stability
    tools.sort(key=lambda t: t.name)
    return tools


def get_deferred_tools(tools: list) -> list:
    """Get tools that should be deferred (not included in initial prompt)."""
    return [t for t in tools if getattr(t, 'should_defer', False)]


def get_loaded_tools(tools: list) -> list:
    """Get tools that should be loaded in initial prompt."""
    return [t for t in tools if not getattr(t, 'should_defer', False)]


def filter_tools_by_deny_rules(tools: list, deny_rules: list) -> list:
    """Remove blanket-denied tools (deny rules with no pattern or empty pattern)."""
    denied_names = set()
    for rule in deny_rules:
        pattern = rule.get("pattern")
        if pattern is None or pattern == "":
            tool_name = rule.get("tool", "")
            if tool_name:
                denied_names.add(tool_name)
    return [t for t in tools if t.name not in denied_names]
