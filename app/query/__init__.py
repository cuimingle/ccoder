"""Core API query function with streaming and tool call loop."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

from app.tool import Tool, ToolResult, ToolContext
from app.types.message import (
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
    Message,
)
from app.services.api.claude import ClaudeAPIClient, StreamEvent
from app.compaction import reactive_compact
from app.message_normalization import normalize_messages_for_api
from app.streaming_tool_executor import StreamingToolExecutor

if TYPE_CHECKING:
    from app.tool_executor import ToolExecutor


@dataclass
class QueryResult:
    response_text: str
    tool_calls: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list[Message] = field(default_factory=list)
    should_exit: bool = False


async def query(
    messages: list[Message],
    system: str,
    tools: list[Tool],
    api_client: ClaudeAPIClient,
    cwd: str,
    permission_mode: str = "manual",
    on_text: Callable[[str], None] | None = None,
    on_tool_use: Callable[[str, dict], None] | None = None,
    tool_executor: "ToolExecutor | None" = None,
    max_continuations: int = 3,
) -> QueryResult:
    """
    Send messages to Claude API and process the streaming response.
    Handles multi-turn tool call loops automatically.
    Returns when the model stops with a text-only response.
    """
    conversation: list[Message] = list(messages)
    all_tool_calls: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    continuation_count = 0
    all_response_parts: list[str] = []
    has_attempted_reactive_compact = False
    context = ToolContext(cwd=cwd, permission_mode=permission_mode)

    while True:
        normalized = normalize_messages_for_api(conversation)
        api_messages = api_client.messages_to_api_format(normalized)
        api_tools = await api_client.tools_to_api_format(tools)
        params = api_client.build_request_params(
            messages=api_messages,
            system=system,
            tools=api_tools,
        )

        # Collect streaming events for this turn
        text_parts: list[str] = []
        tool_use_events: list[StreamEvent] = []
        stop_reason = ""

        try:
            async for event in api_client.stream(params):
                if event.type == "text_delta":
                    text_parts.append(event.text)
                    if on_text:
                        on_text(event.text)
                elif event.type == "tool_use":
                    tool_use_events.append(event)
                    if on_tool_use:
                        on_tool_use(event.tool_name, event.tool_input)
                elif event.type == "usage":
                    total_input_tokens += event.input_tokens
                    total_output_tokens += event.output_tokens
                elif event.type == "message_stop":
                    stop_reason = event.stop_reason
                    break
        except Exception as e:
            if _is_prompt_too_long(e) and not has_attempted_reactive_compact:
                has_attempted_reactive_compact = True
                compacted, comp_in, comp_out = await reactive_compact(
                    conversation, api_client, system
                )
                conversation = compacted
                total_input_tokens += comp_in
                total_output_tokens += comp_out
                continue
            raise

        response_text = "".join(text_parts)

        # Build assistant message for this turn
        assistant_content: list = []
        if response_text:
            assistant_content.append(TextBlock(text=response_text))
        for ev in tool_use_events:
            assistant_content.append(
                ToolUseBlock(id=ev.tool_use_id, name=ev.tool_name, input=ev.tool_input)
            )

        if assistant_content:
            conversation.append(AssistantMessage(content=assistant_content))

        # If no tool calls, check if we need to auto-continue
        if not tool_use_events:
            if (
                stop_reason == "max_output_tokens"
                and continuation_count < max_continuations
            ):
                all_response_parts.append(response_text)
                conversation.append(
                    UserMessage(
                        content="Continue from where you left off. Do not repeat previous content."
                    )
                )
                continuation_count += 1
                continue
            # Include current turn's text in accumulated parts
            all_response_parts.append(response_text)
            break

        # Execute tool calls via StreamingToolExecutor
        if tool_use_events:
            executor = StreamingToolExecutor(
                tools, context=context,
            )
            for ev in tool_use_events:
                executor.add_tool(
                    ToolUseBlock(id=ev.tool_use_id, name=ev.tool_name, input=ev.tool_input)
                )

            tool_result_blocks: list[ToolResultBlock] = []
            idx = 0
            async for result in executor.get_results():
                ev = tool_use_events[idx]
                all_tool_calls.append({
                    "tool_name": ev.tool_name,
                    "tool_use_id": ev.tool_use_id,
                    "input": ev.tool_input,
                    "result": result,
                })
                tool_result_blocks.append(
                    ToolResultBlock(
                        tool_use_id=ev.tool_use_id,
                        content=result.content if isinstance(result.content, str) else str(result.content),
                        is_error=result.is_error,
                    )
                )
                idx += 1

            conversation.append(UserMessage(content=tool_result_blocks))

    return QueryResult(
        response_text="".join(all_response_parts),
        tool_calls=all_tool_calls,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        messages=conversation,
    )


def _is_prompt_too_long(error: Exception) -> bool:
    """Check if an exception indicates a prompt_too_long error."""
    error_str = str(error).lower()
    return "prompt is too long" in error_str or "prompt_too_long" in error_str

