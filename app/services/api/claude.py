"""Anthropic API client — streaming wrapper."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import AsyncIterator, TYPE_CHECKING
import anthropic

if TYPE_CHECKING:
    from app.abort import AbortSignal

DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 8096


@dataclass
class APIRequestParams:
    model: str
    messages: list[dict]
    system: str
    tools: list[dict]
    max_tokens: int = DEFAULT_MAX_TOKENS
    stream: bool = True


@dataclass
class StreamEvent:
    """Normalized stream event from the API."""
    type: str  # "text_delta" | "tool_use" | "message_stop" | "usage"
    text: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""


class ClaudeAPIClient:
    """Wraps the Anthropic SDK with async streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self._api_key = api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.model = model

        # Initialize async client with custom base_url if provided
        if self._base_url:
            self._client = anthropic.AsyncAnthropic(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        else:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

    def build_request_params(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> APIRequestParams:
        return APIRequestParams(
            model=self.model,
            messages=messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
        )

    async def stream(self, params: APIRequestParams) -> AsyncIterator[StreamEvent]:
        """Stream events from the Claude API (fully async)."""
        import json

        # Track stop_reason from message_delta events
        last_stop_reason = ""
        # Track tool_use blocks: id -> accumulated json string
        tool_blocks: dict[str, dict] = {}  # id -> {"name": str, "json": str}
        # Map content block index -> tool_use id for correct association
        index_to_tool_id: dict[int, str] = {}
        # Track the currently active content block index
        current_block_index: int | None = None

        async with self._client.messages.stream(
            model=params.model,
            max_tokens=params.max_tokens,
            system=params.system,
            messages=params.messages,
            tools=params.tools if params.tools else anthropic.NOT_GIVEN,
        ) as stream_ctx:
            async for event in stream_ctx:
                if not hasattr(event, "type"):
                    continue

                if event.type == "content_block_start":
                    idx = getattr(event, "index", None)
                    current_block_index = idx
                    cb = getattr(event, "content_block", None)
                    if cb and getattr(cb, "type", None) == "tool_use":
                        tool_blocks[cb.id] = {"name": cb.name, "json": ""}
                        if idx is not None:
                            index_to_tool_id[idx] = cb.id

                elif event.type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta is None:
                        continue
                    dtype = getattr(delta, "type", None)
                    if dtype == "text_delta":
                        yield StreamEvent(type="text_delta", text=delta.text)
                    elif dtype == "input_json_delta":
                        # Accumulate JSON for the currently active tool block
                        pjson = getattr(delta, "partial_json", "")
                        if current_block_index is not None and current_block_index in index_to_tool_id:
                            tid = index_to_tool_id[current_block_index]
                            tool_blocks[tid]["json"] += pjson

                elif event.type == "content_block_stop":
                    # Emit completed tool_use event using index -> id mapping
                    idx = getattr(event, "index", None)
                    if idx is not None and idx in index_to_tool_id:
                        tid = index_to_tool_id[idx]
                        info = tool_blocks[tid]
                        try:
                            tool_input = json.loads(info["json"]) if info["json"] else {}
                        except json.JSONDecodeError:
                            tool_input = {}
                        yield StreamEvent(
                            type="tool_use",
                            tool_use_id=tid,
                            tool_name=info["name"],
                            tool_input=tool_input,
                        )
                    current_block_index = None

                elif event.type == "message_delta":
                    usage = getattr(event, "usage", None)
                    if usage:
                        yield StreamEvent(
                            type="usage",
                            output_tokens=getattr(usage, "output_tokens", 0),
                        )
                    # Capture stop_reason from message_delta for the final message_stop
                    delta = getattr(event, "delta", None)
                    if delta:
                        sr = getattr(delta, "stop_reason", None)
                        if sr:
                            last_stop_reason = sr

                elif event.type == "message_stop":
                    yield StreamEvent(type="message_stop", stop_reason=last_stop_reason)

    def messages_to_api_format(self, messages: list) -> list[dict]:
        """Convert internal message objects to API dict format."""
        result = []
        for msg in messages:
            if not hasattr(msg, "role"):
                continue
            role = msg.role.value if hasattr(msg.role, "value") else msg.role
            content = msg.content
            if isinstance(content, str):
                result.append({"role": role, "content": content})
            elif isinstance(content, list):
                blocks = []
                for block in content:
                    if not hasattr(block, "type"):
                        continue
                    if block.type == "text":
                        blocks.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        blocks.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                    elif block.type == "tool_result":
                        blocks.append({
                            "type": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "content": block.content,
                            "is_error": block.is_error,
                        })
                if blocks:
                    result.append({"role": role, "content": blocks})
        return result

    async def stream_with_retry(
        self,
        params: APIRequestParams,
        abort_signal: AbortSignal | None = None,
        fallback_model: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream with automatic retry, backoff, and model fallback.

        Wraps :meth:`stream` with :func:`app.services.api.retry.with_retry`.
        """
        from app.services.api.retry import RetryConfig, with_retry

        config = RetryConfig(
            model=params.model,
            fallback_model=fallback_model,
        )

        def _make_stream() -> AsyncIterator[StreamEvent]:
            return self.stream(params)

        async for event in with_retry(_make_stream, config, abort_signal):
            yield event

    async def tools_to_api_format(self, tools: list) -> list[dict]:
        """Convert Tool objects to API dict format."""
        result = []
        for tool in tools:
            if tool.is_enabled():
                result.append({
                    "name": tool.name,
                    "description": await tool.prompt(),
                    "input_schema": tool.input_schema,
                })
        return result