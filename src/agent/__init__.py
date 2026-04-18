"""Arkenstone prospect-research agent.

Public surface:
    from agent import Agent, research
    from agent.brief import Brief
    from agent.tools import ToolRegistry, build_registry
"""

from agent.agent import Agent, AgentResult, research, run
from agent.brief import Brief
from agent.config import Profile, settings

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
