"""QueryEngine — higher-level session orchestrator wrapping query()."""
from __future__ import annotations
from typing import Callable

from app.command_registry import CommandRegistry
from app.commands import build_default_registry, parse_command
from app.compaction import (
    compact_conversation,
    micro_compact_messages,
    should_compact,
)
from app.context import build_system_prompt
from app.hooks import HookRunner
from app.permissions import PermissionChecker
from app.query import query, QueryResult
from app.services.api.claude import ClaudeAPIClient
from app.settings import Settings, load_settings
from app.tool import Tool
from app.tool_executor import PermissionCallback, ToolExecutor
from app.tool_registry import get_tools
from app.types.message import Message, UserMessage
from app.types.permissions import PermissionMode


class QueryEngine:
    """
    Manages conversation state across multiple turns.
    Wraps query() with session bookkeeping.
    Corresponds to QueryEngine.ts in the reference implementation.
    """

    def __init__(
        self,
        cwd: str,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "claude-opus-4-6",
        permission_mode: str = "manual",
        permission_callback: "PermissionCallback | None" = None,
    ):
        self.cwd = cwd
        self.permission_mode = permission_mode
        self.messages: list[Message] = []
        self.turn_count: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self._api_client = ClaudeAPIClient(api_key=api_key, base_url=base_url, model=model)
        self._tools: list[Tool] = get_tools()

        # Load settings and build executor pipeline
        settings = load_settings(cwd)
        mode = PermissionMode(permission_mode)
        self._permission_checker = PermissionChecker(settings, mode)
        self._hook_runner = HookRunner(settings.hooks)
        self._tool_executor = ToolExecutor(
            self._permission_checker, self._hook_runner, permission_callback
        )
        self._command_registry = build_default_registry()
        self._session_id: str = ""

    @property
    def command_registry(self) -> CommandRegistry:
        """The command registry for slash commands."""
        return self._command_registry

    @property
    def model(self) -> str:
        """Current model name."""
        return self._api_client.model

    @model.setter
    def model(self, value: str) -> None:
        """Switch the active model."""
        self._api_client.model = value

    async def run_turn(
        self,
        user_input: str,
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict], None] | None = None,
    ) -> QueryResult:
        """
        Run a single conversation turn.
        Handles slash commands, appends user message, calls query(), updates session state.
        """
        # Handle slash commands
        cmd = parse_command(user_input)
        if cmd is not None:
            command_name, args = cmd
            if command_name == "compact":
                return await self._handle_compact()
            if command_name == "clear":
                self.clear()
                return QueryResult(response_text="Session cleared.", tool_calls=[])

            context = {
                "engine": self,
                "registry": self._command_registry,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "turn_count": self.turn_count,
                "cwd": self.cwd,
                "app_state": getattr(self, "_app_state", None),
            }
            result = await self._command_registry.execute(command_name, args, context)
            qr = QueryResult(response_text=result.text, tool_calls=[])
            qr.should_exit = result.should_exit
            return qr

        self.messages.append(UserMessage(content=user_input))
        system = build_system_prompt(cwd=self.cwd)

        result = await query(
            messages=self.messages,
            system=system,
            tools=self._tools,
            api_client=self._api_client,
            cwd=self.cwd,
            permission_mode=self.permission_mode,
            on_text=on_text,
            on_tool_use=on_tool_use,
            tool_executor=self._tool_executor,
        )

        # Update session state
        self.messages = result.messages
        self.turn_count += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens

        # Auto-compact if needed
        if should_compact(self.total_input_tokens):
            await self._auto_compact()

        return result

    async def _handle_compact(self) -> QueryResult:
        """Handle /compact command."""
        summary_text = await self.compact()
        return QueryResult(
            response_text=f"Conversation compacted.\n\n{summary_text}",
            tool_calls=[],
        )

    async def compact(self) -> str:
        """Compact the conversation and return the summary text."""
        system = build_system_prompt(cwd=self.cwd)
        new_messages, in_tokens, out_tokens = await compact_conversation(
            self.messages, self._api_client, system
        )
        self.messages = new_messages
        self.total_input_tokens += in_tokens
        self.total_output_tokens += out_tokens

        # Extract summary text
        if new_messages and isinstance(new_messages[0].content, str):
            return new_messages[0].content
        return "Conversation compacted."

    async def _auto_compact(self) -> None:
        """Auto-compact: micro-compact first, then full compact if still needed."""
        self.messages = micro_compact_messages(self.messages)
        if should_compact(self.total_input_tokens):
            await self.compact()

    def clear(self) -> None:
        """Reset the session state."""
        self.messages = []
        self.turn_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
