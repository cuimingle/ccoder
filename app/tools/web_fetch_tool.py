"""WebFetchTool — fetch URL, convert HTML to Markdown, with caching."""
from __future__ import annotations
import time
import httpx
import html2text
from app.tool import BaseTool, ToolContext, ToolResult

MAX_CONTENT_LENGTH = 50_000
CACHE_TTL_SECONDS = 900  # 15 minutes

# Simple in-memory cache: url -> (timestamp, content)
_cache: dict[str, tuple[float, str]] = {}

_PROMPT = """\

- Fetches content from a specified URL and processes it using an AI model
- Takes a URL and a prompt as input
- Fetches the URL content, converts HTML to markdown
- Processes the content with the prompt using a small, fast model
- Returns the model's response about the content
- Use this tool when you need to retrieve and analyze web content

Usage notes:
  - IMPORTANT: If an MCP-provided web fetch tool is available, prefer using that \
tool instead of this one, as it may have fewer restrictions.
  - The URL must be a fully-formed valid URL
  - HTTP URLs will be automatically upgraded to HTTPS
  - The prompt should describe what information you want to extract from the page
  - This tool is read-only and does not modify any files
  - Results may be summarized if the content is very large
  - Includes a self-cleaning 15-minute cache for faster responses when repeatedly \
accessing the same URL
  - When a URL redirects to a different host, the tool will inform you and provide \
the redirect URL in a special format. You should then make a new WebFetch request \
with the redirect URL to fetch the content.
  - For GitHub URLs, prefer using the gh CLI via Bash instead \
(e.g., gh pr view, gh issue view, gh api).\
"""


class WebFetchTool(BaseTool):
    name = "WebFetch"

    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt to run on the fetched content",
            },
        },
        "required": ["url", "prompt"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        url = input["url"]
        prompt_text = input.get("prompt", "")

        # Upgrade HTTP to HTTPS
        if url.startswith("http://"):
            url = "https://" + url[7:]

        # Check cache
        now = time.time()
        if url in _cache:
            cached_time, cached_content = _cache[url]
            if now - cached_time < CACHE_TTL_SECONDS:
                return ToolResult(content=cached_content)

        # Clean expired cache entries
        expired = [k for k, (t, _) in _cache.items() if now - t >= CACHE_TTL_SECONDS]
        for k in expired:
            del _cache[k]

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(url)

            # Check for cross-host redirect
            final_url = str(response.url)
            if final_url != url:
                from urllib.parse import urlparse
                orig_host = urlparse(url).netloc
                final_host = urlparse(final_url).netloc
                if orig_host != final_host:
                    return ToolResult(
                        content=f"URL redirected to a different host: {final_url}\n"
                        "Please make a new WebFetch request with the redirect URL."
                    )

            response.raise_for_status()
            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type.lower():
                converter = html2text.HTML2Text()
                converter.ignore_links = False
                converter.ignore_images = True
                markdown = converter.handle(response.text)
            else:
                markdown = response.text

            truncated = markdown[:MAX_CONTENT_LENGTH]
            if len(markdown) > MAX_CONTENT_LENGTH:
                truncated += f"\n\n[Content truncated at {MAX_CONTENT_LENGTH} characters]"

            # Cache the result
            _cache[url] = (now, truncated)

            return ToolResult(content=truncated)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
