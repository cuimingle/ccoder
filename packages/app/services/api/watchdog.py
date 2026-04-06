"""Stream idle-timeout watchdog.

Wraps an async iterator and raises ``StreamIdleTimeout`` when no event
arrives within the configured timeout window.  Matches the TypeScript
90-second stream watchdog.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

STREAM_IDLE_TIMEOUT = 90.0  # seconds
STREAM_IDLE_WARNING = 45.0  # seconds — log a warning at half-timeout


class StreamIdleTimeout(Exception):
    """Raised when a stream goes idle beyond the configured timeout."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        super().__init__(f"Stream idle for {timeout:.0f}s — timed out")


async def watched_stream(
    stream: AsyncIterator[T],
    timeout: float = STREAM_IDLE_TIMEOUT,
) -> AsyncIterator[T]:
    """Wrap *stream* with an idle-timeout guard.

    If no item is yielded within *timeout* seconds, raises
    ``StreamIdleTimeout``.  The timer resets on every item.
    """
    aiter = stream.__aiter__()

    while True:
        try:
            item = await asyncio.wait_for(aiter.__anext__(), timeout=timeout)
            yield item
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            raise StreamIdleTimeout(timeout)
