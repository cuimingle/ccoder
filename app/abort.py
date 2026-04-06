"""AbortController / AbortSignal — Python equivalent of the Web API pattern.

Used to propagate cancellation through the query loop, tool execution, and
streaming layers.
"""
from __future__ import annotations

import asyncio
from typing import Callable


class AbortSignal:
    """Observable cancellation token."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason: str = ""
        self._listeners: list[Callable[[], None]] = []

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)
        # If already aborted, fire immediately
        if self.aborted:
            callback()

    def _fire(self, reason: str) -> None:
        self._reason = reason
        self._event.set()
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass

    async def wait_for_abort(self) -> None:
        """Block until the signal is aborted."""
        await self._event.wait()


class AbortController:
    """Controller that can trigger an AbortSignal."""

    def __init__(self, parent: AbortController | None = None) -> None:
        self._signal = AbortSignal()
        # If a parent is provided, inherit its abort
        if parent is not None:
            parent.signal.add_listener(lambda: self.abort(parent.signal.reason))

    @property
    def signal(self) -> AbortSignal:
        return self._signal

    def abort(self, reason: str = "aborted") -> None:
        if not self._signal.aborted:
            self._signal._fire(reason)

    def child(self) -> AbortController:
        """Create a child controller that aborts when this one does."""
        return AbortController(parent=self)
