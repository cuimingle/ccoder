"""API error classification — structured error handling for the Anthropic API.

Maps raw SDK exceptions to classified error types with retryability info,
matching the TypeScript ``services/api/errors.ts`` patterns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import anthropic


class APIErrorType(str, Enum):
    PROMPT_TOO_LONG = "prompt_too_long"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    IMAGE_SIZE_ERROR = "image_size_error"
    PDF_ERROR = "pdf_error"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    AUTH_ERROR = "auth_error"
    CREDIT_BALANCE_LOW = "credit_balance_low"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    TOOL_USE_MISMATCH = "tool_use_mismatch"
    INVALID_MODEL = "invalid_model"
    SERVER_ERROR = "server_error"
    ABORTED = "aborted"
    UNKNOWN = "unknown"


# User-facing error message constants
PROMPT_TOO_LONG_MESSAGE = "Prompt is too long"
CREDIT_BALANCE_TOO_LOW_MESSAGE = "Credit balance is too low"
INVALID_API_KEY_MESSAGE = "Not logged in · Please run /login or set ANTHROPIC_API_KEY"
API_TIMEOUT_MESSAGE = "Request timed out"
API_ERROR_PREFIX = "API Error"


@dataclass
class ClassifiedError:
    """A classified API error with structured metadata."""

    type: APIErrorType
    original: Exception
    message: str
    status_code: int | None = None
    retry_after: float | None = None
    is_retryable: bool = False
    raw_api_message: str = ""


def classify_error(error: Exception) -> ClassifiedError:
    """Classify an exception into a structured API error type."""

    # User abort — check by class name since SDK versions vary
    error_name = type(error).__name__
    if error_name in ("APIUserAbortError", "UserAbortError") or "abort" in str(error).lower():
        # Only match if it's an anthropic error or explicit abort
        if isinstance(error, anthropic.AnthropicError) or error_name in ("APIUserAbortError", "UserAbortError"):
            return ClassifiedError(
                type=APIErrorType.ABORTED,
                original=error,
                message="Request aborted",
                is_retryable=False,
            )

    # Connection timeout
    if isinstance(error, anthropic.APITimeoutError):
        return ClassifiedError(
            type=APIErrorType.TIMEOUT,
            original=error,
            message=API_TIMEOUT_MESSAGE,
            is_retryable=True,
        )

    # Network / connection error
    if isinstance(error, anthropic.APIConnectionError):
        return ClassifiedError(
            type=APIErrorType.NETWORK_ERROR,
            original=error,
            message=f"Connection error: {error}",
            is_retryable=True,
        )

    # HTTP status errors
    if isinstance(error, anthropic.APIStatusError):
        return _classify_status_error(error)

    # Generic exception — check string for known patterns
    error_str = str(error)
    if _is_prompt_too_long_body(error_str):
        return ClassifiedError(
            type=APIErrorType.PROMPT_TOO_LONG,
            original=error,
            message=PROMPT_TOO_LONG_MESSAGE,
            is_retryable=False,
            raw_api_message=error_str,
        )

    # Generic fallback
    return ClassifiedError(
        type=APIErrorType.UNKNOWN,
        original=error,
        message=error_str,
        is_retryable=False,
    )


def _classify_status_error(error: anthropic.APIStatusError) -> ClassifiedError:
    """Classify an HTTP status error from the Anthropic API."""
    status = error.status_code
    body = _extract_error_body(error)
    raw_msg = body.get("message", str(error))

    # 401 — authentication
    if status == 401:
        return ClassifiedError(
            type=APIErrorType.AUTH_ERROR,
            original=error,
            message=INVALID_API_KEY_MESSAGE,
            status_code=status,
            is_retryable=False,
        )

    # 403 — forbidden / org disabled / credit balance
    if status == 403:
        if "credit balance" in raw_msg.lower():
            return ClassifiedError(
                type=APIErrorType.CREDIT_BALANCE_LOW,
                original=error,
                message=CREDIT_BALANCE_TOO_LOW_MESSAGE,
                status_code=status,
                is_retryable=False,
            )
        return ClassifiedError(
            type=APIErrorType.AUTH_ERROR,
            original=error,
            message=raw_msg,
            status_code=status,
            is_retryable=False,
        )

    # 429 — rate limit
    if status == 429:
        retry_after = _parse_retry_after(error)
        return ClassifiedError(
            type=APIErrorType.RATE_LIMIT,
            original=error,
            message=f"Rate limited. {raw_msg}",
            status_code=status,
            retry_after=retry_after,
            is_retryable=True,
        )

    # 413 / prompt too long (can also come as 400)
    if _is_prompt_too_long_body(raw_msg):
        return ClassifiedError(
            type=APIErrorType.PROMPT_TOO_LONG,
            original=error,
            message=PROMPT_TOO_LONG_MESSAGE,
            status_code=status,
            is_retryable=False,
            raw_api_message=raw_msg,
        )

    # 400 — various
    if status == 400:
        if _is_media_size_body(raw_msg):
            return ClassifiedError(
                type=APIErrorType.IMAGE_SIZE_ERROR,
                original=error,
                message=raw_msg,
                status_code=status,
                is_retryable=False,
                raw_api_message=raw_msg,
            )
        if "pdf" in raw_msg.lower():
            return ClassifiedError(
                type=APIErrorType.PDF_ERROR,
                original=error,
                message=raw_msg,
                status_code=status,
                is_retryable=False,
                raw_api_message=raw_msg,
            )
        if "tool_use" in raw_msg.lower() or "tool_result" in raw_msg.lower():
            return ClassifiedError(
                type=APIErrorType.TOOL_USE_MISMATCH,
                original=error,
                message=raw_msg,
                status_code=status,
                is_retryable=False,
            )
        if "model" in raw_msg.lower() and "not found" in raw_msg.lower():
            return ClassifiedError(
                type=APIErrorType.INVALID_MODEL,
                original=error,
                message=raw_msg,
                status_code=status,
                is_retryable=False,
            )

    # 529 — overloaded
    if status == 529:
        retry_after = _parse_retry_after(error)
        return ClassifiedError(
            type=APIErrorType.OVERLOADED,
            original=error,
            message=f"API overloaded. {raw_msg}",
            status_code=status,
            retry_after=retry_after,
            is_retryable=True,
        )

    # 500+ — server errors
    if status >= 500:
        return ClassifiedError(
            type=APIErrorType.SERVER_ERROR,
            original=error,
            message=f"{API_ERROR_PREFIX}: {raw_msg}",
            status_code=status,
            is_retryable=True,
        )

    # Generic fallback for unclassified status codes
    return ClassifiedError(
        type=APIErrorType.UNKNOWN,
        original=error,
        message=f"{API_ERROR_PREFIX} ({status}): {raw_msg}",
        status_code=status,
        is_retryable=False,
    )


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------

def is_prompt_too_long(error: Exception) -> bool:
    """Check if an exception indicates a prompt_too_long error."""
    classified = classify_error(error)
    return classified.type == APIErrorType.PROMPT_TOO_LONG


def is_max_output_tokens(stop_reason: str) -> bool:
    """Check if the stop reason indicates max output tokens."""
    return stop_reason in ("max_tokens", "max_output_tokens")


def is_media_size_error(error: Exception) -> bool:
    """Check if an exception indicates an image/media size error."""
    classified = classify_error(error)
    return classified.type == APIErrorType.IMAGE_SIZE_ERROR


def is_overloaded(error: Exception) -> bool:
    """Check if an exception indicates API overload (529)."""
    classified = classify_error(error)
    return classified.type == APIErrorType.OVERLOADED


_PTL_TOKEN_RE = re.compile(
    r"prompt is too long[^0-9]*(\d+)\s*tokens?\s*>\s*(\d+)", re.IGNORECASE
)


def parse_prompt_too_long_token_counts(raw_message: str) -> tuple[int, int] | None:
    """Extract (actual_tokens, limit_tokens) from a prompt-too-long error message."""
    m = _PTL_TOKEN_RE.search(raw_message)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_error_body(error: anthropic.APIStatusError) -> dict[str, Any]:
    """Safely extract the JSON body from an API status error."""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            return err
    return {"message": str(error)}


def _is_prompt_too_long_body(msg: str) -> bool:
    lower = msg.lower()
    return "prompt is too long" in lower or "prompt_too_long" in lower


def _is_media_size_body(msg: str) -> bool:
    lower = msg.lower()
    return (
        "image exceeds" in lower
        or "image dimensions exceed" in lower
        or "maximum of" in lower and "pdf pages" in lower
    )


def _parse_retry_after(error: anthropic.APIStatusError) -> float | None:
    """Parse retry-after header from the error response."""
    headers = getattr(error, "response", None)
    if headers is not None:
        headers = getattr(headers, "headers", None)
    if headers is None:
        return None
    val = headers.get("retry-after")
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return None
