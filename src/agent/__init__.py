"""Claude-powered agent template.

Public surface:
    from agent import Agent, run
    from agent.tools import tool, ToolRegistry
    from agent.config import settings
"""

from agent.agent import Agent, AgentResult, run
from agent.config import Profile, settings

__all__ = ["Agent", "AgentResult", "Profile", "run", "settings"]
__version__ = "0.1.0"
