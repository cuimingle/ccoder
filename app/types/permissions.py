"""Permission mode and result types."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class PermissionMode(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"
    PLAN = "plan"


class PermissionResult(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ALLOW_ALWAYS = "allow_always"
    DENY_ALWAYS = "deny_always"
    ASK_USER = "ask_user"


@dataclass
class PermissionDecision:
    result: PermissionResult
    reason: str = ""
