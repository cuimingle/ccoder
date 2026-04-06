"""SkillTool — execute skills (slash commands) within the conversation."""
from __future__ import annotations
from app.tool import BaseTool, ToolContext, ToolResult

_PROMPT = """\
Execute a skill within the main conversation

When users ask you to perform tasks, check if any of the available skills match. \
Skills provide specialized capabilities and domain knowledge.

When users reference a "slash command" or "/<something>" (e.g., "/commit", "/review-pr"), \
they are referring to a skill. Use this tool to invoke it.

How to invoke:
- Use this tool with the skill name and optional arguments
- Examples:
  - `skill: "pdf"` - invoke the pdf skill
  - `skill: "commit", args: "-m 'Fix bug'"` - invoke with arguments
  - `skill: "review-pr", args: "123"` - invoke with arguments
  - `skill: "ms-office-suite:pdf"` - invoke using fully qualified name

Important:
- Available skills are listed in system-reminder messages in the conversation
- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: invoke \
the relevant Skill tool BEFORE generating any other response about the task
- NEVER mention a skill without actually calling this tool
- Do not invoke a skill that is already running
- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)
- If you see a <command-name> tag in the current conversation turn, the skill has \
ALREADY been loaded - follow the instructions directly instead of calling this tool again\
"""


class SkillTool(BaseTool):
    name = "Skill"
    search_hint = "execute skill slash command invoke"

    input_schema = {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": 'The skill name. E.g., "commit", "review-pr", or "pdf"',
            },
            "args": {
                "type": "string",
                "description": "Optional arguments for the skill",
            },
        },
        "required": ["skill"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        skill_name = input_data["skill"]
        args = input_data.get("args", "")

        # Look up skill in command registry
        try:
            from app.commands import build_default_registry
            registry = build_default_registry()
            command_input = f"/{skill_name}" + (f" {args}" if args else "")

            # Check if it's a registered command
            from app.commands import parse_command
            parsed = parse_command(command_input)
            if parsed is None:
                return ToolResult(
                    content=f"Skill '{skill_name}' not found. Available skills are "
                    "listed in system-reminder messages.",
                    is_error=True,
                )

            cmd_name, cmd_args = parsed
            result = await registry.execute(cmd_name, cmd_args, context={})
            if result is not None:
                return ToolResult(content=result.output or f"Skill '{skill_name}' executed.")
            return ToolResult(content=f"Skill '{skill_name}' executed successfully.")
        except ImportError:
            return ToolResult(
                content=f"Skill system not available. Cannot execute '{skill_name}'.",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
