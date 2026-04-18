"""Permission scopes. Default-deny access control for tools.

Each tool call goes through the permissions check. A tool is only allowed
to run if its name is in the allow_list for the active scope.

Recommended pattern: have one PermissionScope per caller context (e.g.
"admin_ops" vs "customer_facing") and choose the scope at agent construction
time based on who the caller is.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class PermissionDenied(Exception):
    """Raised when a tool call is rejected by the active scope."""


@dataclass
class PermissionScope:
    """A named set of tools this agent is allowed to call.

    Example:
        read_only = PermissionScope(
            name="read_only",
            allow_list={"get_user", "search_docs"},
        )
        admin = PermissionScope(
            name="admin",
            allow_list={"get_user", "search_docs", "refund_order"},
            require_confirmation={"refund_order"},
        )
    """

    name: str
    allow_list: set[str] = field(default_factory=set)
    require_confirmation: set[str] = field(default_factory=set)
    """Tools in this set will raise PendingConfirmation instead of running,
    yielding to the human-in-the-loop module."""

    def check(self, tool_name: str) -> None:
        if tool_name not in self.allow_list:
            raise PermissionDenied(
                f"Scope {self.name!r} does not permit tool {tool_name!r}"
            )

    def needs_confirmation(self, tool_name: str) -> bool:
        return tool_name in self.require_confirmation


# Convenience: a scope that allows everything. Use for dev only.
UNRESTRICTED = PermissionScope(name="unrestricted", allow_list=set())
UNRESTRICTED.check = lambda _tool_name: None  # type: ignore[assignment]
