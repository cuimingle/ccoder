"""Cron tools — CronCreate, CronList, CronDelete for scheduling."""
from __future__ import annotations
import json
import uuid
from app.tool import BaseTool, ToolContext, ToolResult

# In-memory cron store keyed by session_id
_cron_stores: dict[str, list[dict]] = {}


def _get_cron_store(session_id: str) -> list[dict]:
    if session_id not in _cron_stores:
        _cron_stores[session_id] = []
    return _cron_stores[session_id]


# ──────────────────────────────────────────────────────────────────────
# CronCreate
# ──────────────────────────────────────────────────────────────────────

_CRON_CREATE_PROMPT = """\
Schedule a prompt to be enqueued at a future time. Use for both recurring schedules \
and one-shot reminders.

Uses standard 5-field cron in the user's local timezone: minute hour day-of-month month \
day-of-week. "0 9 * * *" means 9am local \u2014 no timezone conversion needed.

## One-shot tasks (recurring: false)

For "remind me at X" or "at <time>, do Y" requests \u2014 fire once then auto-delete.
Pin minute/hour/day-of-month/month to specific values:
  "remind me at 2:30pm today to check the deploy" \u2192 \
cron: "30 14 <today_dom> <today_month> *", recurring: false
  "tomorrow morning, run the smoke test" \u2192 \
cron: "57 8 <tomorrow_dom> <tomorrow_month> *", recurring: false

## Recurring jobs (recurring: true, the default)

For "every N minutes" / "every hour" / "weekdays at 9am" requests:
  "*/5 * * * *" (every 5 min), "0 * * * *" (hourly), \
"0 9 * * 1-5" (weekdays at 9am local)

## Avoid the :00 and :30 minute marks when the task allows it

Every user who asks for "9am" gets `0 9`, and every user who asks for "hourly" gets \
`0 *` \u2014 which means requests from across the planet land on the API at the same \
instant. When the user's request is approximate, pick a minute that is NOT 0 or 30:
  "every morning around 9" \u2192 "57 8 * * *" or "3 9 * * *" (not "0 9 * * *")
  "hourly" \u2192 "7 * * * *" (not "0 * * * *")
  "in an hour or so, remind me to..." \u2192 pick whatever minute you land on, \
don't round

Only use minute 0 or 30 when the user names that exact time and clearly means it \
("at 9:00 sharp", "at half past", coordinating with a meeting). When in doubt, nudge \
a few minutes early or late \u2014 the user will not notice, and the fleet will.

## Runtime behavior

Jobs only fire while the REPL is idle (not mid-query). Session-only jobs die with the \
process. The scheduler adds a small deterministic jitter. Recurring tasks auto-expire \
after 14 days \u2014 they fire one final time, then are deleted. Tell the user about \
the 14-day limit when scheduling recurring jobs.

Returns a job ID you can pass to CronDelete.\
"""


class CronCreateTool(BaseTool):
    name = "CronCreate"
    search_hint = "schedule cron job recurring one-shot timer"

    input_schema = {
        "type": "object",
        "properties": {
            "cron": {
                "type": "string",
                "description": (
                    "Standard 5-field cron expression in local time "
                    "(minute hour dom month dow)"
                ),
            },
            "prompt": {
                "type": "string",
                "description": "Prompt to enqueue at fire time",
            },
            "recurring": {
                "type": "boolean",
                "description": "true (default) for recurring, false for one-shot",
            },
        },
        "required": ["cron", "prompt"],
    }

    async def prompt(self) -> str:
        return _CRON_CREATE_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        cron_expr = input_data["cron"]
        prompt_text = input_data["prompt"]
        recurring = input_data.get("recurring", True)

        # Validate cron expression (basic: 5 fields)
        fields = cron_expr.strip().split()
        if len(fields) != 5:
            return ToolResult(
                content=f"Invalid cron expression: expected 5 fields, got {len(fields)}",
                is_error=True,
            )

        job_id = uuid.uuid4().hex[:8]
        store = _get_cron_store(context.session_id)
        job = {
            "id": job_id,
            "cron": cron_expr,
            "prompt": prompt_text,
            "recurring": recurring,
            "humanSchedule": _humanize_cron(cron_expr, recurring),
        }
        store.append(job)

        return ToolResult(
            content=json.dumps(
                {
                    "id": job_id,
                    "humanSchedule": job["humanSchedule"],
                    "recurring": recurring,
                },
                ensure_ascii=False,
            )
        )


def _humanize_cron(cron: str, recurring: bool) -> str:
    """Simple human-readable description of a cron expression."""
    fields = cron.split()
    if len(fields) != 5:
        return cron

    minute, hour, dom, month, dow = fields

    if recurring:
        if minute.startswith("*/"):
            return f"Every {minute[2:]} minutes"
        if hour == "*" and minute != "*":
            return f"Every hour at :{minute}"
        if dom == "*" and month == "*":
            if dow == "*":
                return f"Daily at {hour}:{minute.zfill(2)}"
            return f"At {hour}:{minute.zfill(2)} on days {dow}"
    else:
        return f"Once at {hour}:{minute.zfill(2)} on {month}/{dom}"

    return cron


# ──────────────────────────────────────────────────────────────────────
# CronList
# ──────────────────────────────────────────────────────────────────────

_CRON_LIST_PROMPT = """\
List all cron jobs scheduled via CronCreate in this session.\
"""


class CronListTool(BaseTool):
    name = "CronList"
    search_hint = "list scheduled cron jobs"

    input_schema = {"type": "object", "properties": {}}

    async def prompt(self) -> str:
        return _CRON_LIST_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        store = _get_cron_store(context.session_id)
        if not store:
            return ToolResult(content="No scheduled cron jobs.")
        return ToolResult(
            content=json.dumps({"jobs": store}, ensure_ascii=False, indent=2)
        )


# ──────────────────────────────────────────────────────────────────────
# CronDelete
# ──────────────────────────────────────────────────────────────────────

_CRON_DELETE_PROMPT = """\
Cancel a cron job previously scheduled with CronCreate. Removes it from \
the in-memory session store.\
"""


class CronDeleteTool(BaseTool):
    name = "CronDelete"
    search_hint = "cancel delete scheduled cron job"

    input_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Job ID returned by CronCreate",
            },
        },
        "required": ["id"],
    }

    async def prompt(self) -> str:
        return _CRON_DELETE_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        job_id = input_data["id"]
        store = _get_cron_store(context.session_id)
        for i, job in enumerate(store):
            if job["id"] == job_id:
                store.pop(i)
                return ToolResult(
                    content=json.dumps({"id": job_id}, ensure_ascii=False)
                )
        return ToolResult(content=f"Job '{job_id}' not found", is_error=True)
