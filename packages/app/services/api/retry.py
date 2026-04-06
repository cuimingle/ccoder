"""Retry logic with exponential backoff for the Anthropic API.

Matches TypeScript ``withRetry`` behavior: exponential backoff with jitter,
consecutive 529 tracking, and model fallback triggering.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, TypeVar

from app.abort import AbortSignal
from app.services.api.errors import (
    APIErrorType,
    ClassifiedError,
    classify_error,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for the retry wrapper."""
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    consecutive_529_limit: int = 3
    fallback_model: str | None = None
    model: str = ""


class FallbackTriggeredError(Exception):
    """Raised when consecutive 529 errors exceed the limit and a fallback model is available."""

    def __init__(self, original_model: str, fallback_model: str) -> None:
        self.original_model = original_model
        self.fallback_model = fallback_model
        super().__init__(
            f"Switched to {fallback_model} due to high demand for {original_model}"
        )


class CannotRetryError(Exception):
    """Raised when an error is not retryable."""

    def __init__(self, original: Exception, classified: ClassifiedError) -> None:
        self.original = original
        self.classified = classified
        super().__init__(str(original))


async def with_retry(
    operation: Callable[[], AsyncIterator],
    config: RetryConfig,
    abort_signal: AbortSignal | None = None,
) -> AsyncIterator:
    """Wrap a streaming operation with retry, backoff, and model fallback.

    Parameters
    ----------
    operation:
        A callable that returns an async iterator (e.g., the API streaming call).
        Will be called fresh on each retry attempt.
    config:
        Retry configuration.
    abort_signal:
        Optional signal to cancel retries.

    Yields
    ------
    Whatever the underlying operation yields.

    Raises
    ------
    FallbackTriggeredError
        When consecutive 529s exceed the limit and a fallback model exists.
    CannotRetryError
        When the error is not retryable.
    """
    consecutive_529 = 0

    for attempt in range(1, config.max_retries + 2):  # +1 for initial + max_retries
        if abort_signal and abort_signal.aborted:
            return

        try:
            async for item in operation():
                yield item
            return  # Success — stream completed
        except Exception as exc:
            classified = classify_error(exc)

            # Not retryable → fail immediately
            if not classified.is_retryable:
                raise CannotRetryError(exc, classified) from exc

            # Track consecutive 529s (overloaded)
            if classified.type == APIErrorType.OVERLOADED:
                consecutive_529 += 1
                if (
                    consecutive_529 >= config.consecutive_529_limit
                    and config.fallback_model
                ):
                    raise FallbackTriggeredError(
                        config.model, config.fallback_model
                    ) from exc
            else:
                consecutive_529 = 0

            # Last attempt — no more retries
            if attempt > config.max_retries:
                raise CannotRetryError(exc, classified) from exc

            # Compute delay
            delay = _compute_delay(attempt, config, classified)
            logger.warning(
                "API error (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                config.max_retries + 1,
                classified.message,
                delay,
            )

            # Sleep with abort check
            if abort_signal:
                try:
                    await asyncio.wait_for(
                        abort_signal.wait_for_abort(), timeout=delay
                    )
                    return  # Aborted during sleep
                except asyncio.TimeoutError:
                    pass  # Sleep completed, proceed to retry
            else:
                await asyncio.sleep(delay)


def _compute_delay(
    attempt: int, config: RetryConfig, classified: ClassifiedError
) -> float:
    """Compute the retry delay with exponential backoff and optional jitter."""
    # Use retry-after header if available
    if classified.retry_after is not None and classified.retry_after > 0:
        return min(classified.retry_after, config.max_delay)

    delay = config.initial_delay * (config.backoff_factor ** (attempt - 1))
    delay = min(delay, config.max_delay)

    if config.jitter:
        delay = delay * (0.5 + random.random() * 0.5)

    return delay
