"""Dependency injection for the query loop.

Provides a Protocol for test mocking and a production implementation
that wires up real services.  Matches TypeScript ``query/deps.ts``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Protocol
from uuid import uuid4

from app.compaction import (
    auto_compact_if_needed,
    AutoCompactResult,
    micro_compact_messages,
)
from app.services.api.claude import APIRequestParams, StreamEvent

if TYPE_CHECKING:
    from app.abort import AbortSignal
    from app.services.api.claude import ClaudeAPIClient
    from app.types.message import Message


class QueryDeps(Protocol):
    """Protocol for query loop dependencies (enables test mocking)."""

    async def call_model(
        self, params: APIRequestParams, abort_signal: AbortSignal | None = None
    ) -> AsyncIterator[StreamEvent]: ...

    def microcompact(self, messages: list[Message]) -> list[Message]: ...

    async def autocompact(
        self,
        messages: list[Message],
        api_client: ClaudeAPIClient,
        system: str,
        total_input_tokens: int,
        consecutive_failures: int,
    ) -> AutoCompactResult: ...

    def uuid(self) -> str: ...


class ProductionDeps:
    """Production implementations of query dependencies."""

    def __init__(self, api_client: ClaudeAPIClient) -> None:
        self._api_client = api_client

    async def call_model(
        self, params: APIRequestParams, abort_signal: AbortSignal | None = None
    ) -> AsyncIterator[StreamEvent]:
        return self._api_client.stream_with_retry(params, abort_signal=abort_signal)

    def microcompact(self, messages: list[Message]) -> list[Message]:
        return micro_compact_messages(messages)

    async def autocompact(
        self,
        messages: list[Message],
        api_client: ClaudeAPIClient,
        system: str,
        total_input_tokens: int,
        consecutive_failures: int = 0,
    ) -> AutoCompactResult:
        return await auto_compact_if_needed(
            messages,
            api_client,
            system,
            total_input_tokens,
            consecutive_failures,
        )

    def uuid(self) -> str:
        return str(uuid4())
