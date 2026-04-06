"""WebSearchTool — search the web using Brave Search API."""
from __future__ import annotations
import os
import httpx
from datetime import datetime
from urllib.parse import urlparse
from app.tool import BaseTool, ToolContext, ToolResult


def _get_prompt() -> str:
    current_month_year = datetime.now().strftime("%B %Y")
    return f"""\

- Allows Claude to search the web and use the results to inform responses
- Provides up-to-date information for current events and recent data
- Returns search result information formatted as search result blocks, \
including links as markdown hyperlinks
- Use this tool for accessing information beyond Claude's knowledge cutoff
- Searches are performed automatically within a single API call

CRITICAL REQUIREMENT - You MUST follow this:
  - After answering the user's question, you MUST include a "Sources:" section \
at the end of your response
  - In the Sources section, list all relevant URLs from the search results as \
markdown hyperlinks: [Title](URL)
  - This is MANDATORY - never skip including sources in your response
  - Example format:

    [Your answer here]

    Sources:
    - [Source Title 1](https://example.com/1)
    - [Source Title 2](https://example.com/2)

Usage notes:
  - Domain filtering is supported to include or block specific websites
  - Web search is only available in the US

IMPORTANT - Use the correct year in search queries:
  - The current month is {current_month_year}. You MUST use this year when \
searching for recent information, documentation, or current events.
  - Example: If the user asks for "latest React docs", search for \
"React documentation" with the current year, NOT last year\
"""


class WebSearchTool(BaseTool):
    name = "WebSearch"

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to use",
            },
            "allowed_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include search results from these domains",
            },
            "blocked_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Never include search results from these domains",
            },
        },
        "required": ["query"],
    }

    async def prompt(self) -> str:
        return _get_prompt()

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        api_key = os.environ.get("BRAVE_API_KEY")
        if not api_key:
            return ToolResult(
                content="WebSearch not configured: BRAVE_API_KEY environment variable not set.",
                is_error=True,
            )
        query = input["query"]
        allowed_domains = input.get("allowed_domains", [])
        blocked_domains = input.get("blocked_domains", [])

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                    },
                    params={"q": query, "count": 10},
                )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", data.get("web", {}).get("results", []))

            # Apply domain filtering
            if allowed_domains:
                results = [
                    r
                    for r in results
                    if any(
                        urlparse(r.get("url", "")).netloc.endswith(d)
                        for d in allowed_domains
                    )
                ]
            if blocked_domains:
                results = [
                    r
                    for r in results
                    if not any(
                        urlparse(r.get("url", "")).netloc.endswith(d)
                        for d in blocked_domains
                    )
                ]

            lines = []
            for r in results[:10]:
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("content", r.get("description", ""))
                lines.append(f"**{title}**\n{url}\n{snippet}\n")

            return ToolResult(
                content="\n".join(lines) if lines else "No results found."
            )
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
