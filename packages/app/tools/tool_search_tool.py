"""ToolSearchTool — fetch full schema definitions for deferred tools."""
from __future__ import annotations
import json
from app.tool import BaseTool, ToolContext, ToolResult

_PROMPT = """\
Fetches full schema definitions for deferred tools so they can be called.

Deferred tools appear by name in <system-reminder> messages. Until fetched, only the \
name is known \u2014 there is no parameter schema, so the tool cannot be invoked. This \
tool takes a query, matches it against the deferred tool list, and returns the matched \
tools' complete JSONSchema definitions inside a <functions> block. Once a tool's schema \
appears in that result, it is callable exactly like any tool defined at the top of the prompt.

Result format: each matched tool appears as one \
<function>{"description": "...", "name": "...", "parameters": {...}}</function> line \
inside the <functions> block \u2014 the same encoding as the tool list at the top of \
this prompt.

Query forms:
- "select:Read,Edit,Grep" \u2014 fetch these exact tools by name
- "notebook jupyter" \u2014 keyword search, up to max_results best matches
- "+slack send" \u2014 require "slack" in the name, rank by remaining terms\
"""


class ToolSearchTool(BaseTool):
    name = "ToolSearch"
    search_hint = "fetch deferred tool schema definitions"
    always_load = True  # Never defer this tool

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    'Query to find deferred tools. Use "select:<tool_name>" for '
                    "direct selection, or keywords to search."
                ),
            },
            "max_results": {
                "type": "number",
                "default": 5,
                "description": "Maximum number of results to return (default: 5)",
            },
        },
        "required": ["query", "max_results"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        query = input_data["query"]
        max_results = int(input_data.get("max_results", 5))

        # Get all tools from registry
        try:
            from app.tool_registry import get_all_base_tools
            all_tools = get_all_base_tools()
        except ImportError:
            return ToolResult(
                content="Tool registry not available.", is_error=True
            )

        # Get deferred tools
        deferred = [t for t in all_tools if getattr(t, "should_defer", False)]
        if not deferred:
            # If no deferred tools, search all tools
            deferred = all_tools

        matched = []

        if query.startswith("select:"):
            # Direct selection: "select:Read,Edit,Grep"
            names = [n.strip() for n in query[7:].split(",")]
            for tool in deferred:
                if tool.name in names or (
                    hasattr(tool, "aliases")
                    and any(a in names for a in tool.aliases)
                ):
                    matched.append(tool)
        elif query.startswith("+"):
            # Require name match: "+slack send"
            parts = query[1:].strip().split()
            required = parts[0].lower() if parts else ""
            keywords = [p.lower() for p in parts[1:]]
            for tool in deferred:
                name_lower = tool.name.lower()
                if required in name_lower:
                    score = sum(
                        1
                        for kw in keywords
                        if kw in name_lower
                        or kw in getattr(tool, "search_hint", "").lower()
                    )
                    matched.append((score, tool))
            matched.sort(key=lambda x: -x[0])
            matched = [t for _, t in matched[:max_results]]
        else:
            # Keyword search
            keywords = [k.lower() for k in query.split()]
            scored = []
            for tool in deferred:
                name_lower = tool.name.lower()
                hint_lower = getattr(tool, "search_hint", "").lower()
                score = sum(
                    1 for kw in keywords if kw in name_lower or kw in hint_lower
                )
                if score > 0:
                    scored.append((score, tool))
            scored.sort(key=lambda x: -x[0])
            matched = [t for _, t in scored[:max_results]]

        if not matched:
            return ToolResult(content="No matching tools found.")

        # Build <functions> block
        functions = []
        for tool in matched:
            tool_def = {
                "name": tool.name,
                "description": getattr(tool, "search_hint", "") or tool.name,
                "parameters": tool.input_schema,
            }
            functions.append(
                f'<function>{json.dumps(tool_def, ensure_ascii=False)}</function>'
            )

        result = "<functions>\n" + "\n".join(functions) + "\n</functions>"
        return ToolResult(content=result)
