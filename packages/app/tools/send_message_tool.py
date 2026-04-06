"""SendMessageTool — send messages to other agents/teammates."""
from __future__ import annotations
import json
from app.tool import BaseTool, ToolContext, ToolResult

_PROMPT = """\
# SendMessage

Send a message to another agent.

```json
{"to": "researcher", "summary": "assign task 1", "message": "start on task #1"}
```

| `to` | |
|---|---|
| `"researcher"` | Teammate by name |
| `"*"` | Broadcast to all teammates \u2014 expensive (linear in team size), use only \
when everyone genuinely needs it |

Your plain text output is NOT visible to other agents \u2014 to communicate, you MUST \
call this tool. Messages from teammates are delivered automatically; you don't check an \
inbox. Refer to teammates by name, never by UUID. When relaying, don't quote the \
original \u2014 it's already rendered to the user.

## Protocol responses (legacy)

If you receive a JSON message with `type: "shutdown_request"` or \
`type: "plan_approval_request"`, respond with the matching `_response` type \u2014 \
echo the `request_id`, set `approve` true/false:

```json
{"to": "team-lead", "message": {"type": "shutdown_response", "request_id": "...", \
"approve": true}}
{"to": "researcher", "message": {"type": "plan_approval_response", "request_id": "...", \
"approve": false, "feedback": "add error handling"}}
```

Approving shutdown terminates your process. Rejecting plan sends the teammate back to \
revise. Don't originate `shutdown_request` unless asked. Don't send structured JSON \
status messages \u2014 use TaskUpdate.\
"""


class SendMessageTool(BaseTool):
    name = "SendMessage"
    search_hint = "send message teammate agent communicate"

    input_schema = {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": (
                    'Recipient: teammate name, or "*" for broadcast to all teammates'
                ),
            },
            "summary": {
                "type": "string",
                "description": (
                    "A 5-10 word summary shown as a preview in the UI "
                    "(required when message is a string)"
                ),
            },
            "message": {
                "type": "string",
                "description": "Plain text message content",
            },
        },
        "required": ["to", "message"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        to = input_data["to"]
        message = input_data["message"]
        summary = input_data.get("summary", "")

        # In the current single-agent implementation, this is a placeholder
        # that will be wired up when multi-agent support is added
        return ToolResult(
            content=f"Message sent to '{to}'" + (f": {summary}" if summary else "")
        )
