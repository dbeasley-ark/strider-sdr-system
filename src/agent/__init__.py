"""Arkenstone prospect-research agent.

Public surface (lazy-loaded so lightweight imports like ``spreadsheet_import``
do not require API keys):

    from agent import Agent, research
    from agent.brief import Brief
    from agent.tools import ToolRegistry, build_registry
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "Agent",
    "AgentResult",
    "Brief",
    "Profile",
    "research",
    "run",
    "settings",
]
__version__ = "0.1.0"


def __getattr__(name: str) -> Any:
    if name in ("Agent", "AgentResult", "research", "run"):
        from agent.agent import Agent, AgentResult, research, run

        if name == "Agent":
            return Agent
        if name == "AgentResult":
            return AgentResult
        if name == "research":
            return research
        return run
    if name == "Brief":
        from agent.brief import Brief

        return Brief
    if name == "Profile":
        from agent.config import Profile

        return Profile
    if name == "settings":
        from agent.config import settings

        return settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
