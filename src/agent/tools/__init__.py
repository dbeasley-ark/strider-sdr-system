"""Tool contracts and registry.

`build_registry()` assembles the canonical tool set for a prospect-
research run. The native `web_search` tool is NOT registered here —
it's a server-side Anthropic tool, attached directly in `Agent._call_llm`.
"""

from __future__ import annotations

from agent.tools._base import Tool, ToolContractError, ToolExecutionError
from agent.tools.fetch_company_page import FetchCompanyPage
from agent.tools.lookup_fedramp_marketplace_products import LookupFedrampMarketplaceProducts
from agent.tools.lookup_sam_registration import LookupSamRegistration
from agent.tools.lookup_sbir_awards import LookupSbirAwards
from agent.tools.lookup_usaspending_awards import LookupUSAspendingAwards
from agent.tools.registry import ToolRegistry

__all__ = [
    "FetchCompanyPage",
    "LookupFedrampMarketplaceProducts",
    "LookupSamRegistration",
    "LookupSbirAwards",
    "LookupUSAspendingAwards",
    "Tool",
    "ToolContractError",
    "ToolExecutionError",
    "ToolRegistry",
    "build_registry",
]


def build_registry() -> ToolRegistry:
    """Construct a ToolRegistry with every custom tool the agent uses.

    Custom tools for spec §4.x. `web_search` is attached separately by the agent.
    """
    registry = ToolRegistry()
    registry.register(LookupSamRegistration())
    registry.register(LookupUSAspendingAwards())
    registry.register(LookupSbirAwards())
    registry.register(LookupFedrampMarketplaceProducts())
    registry.register(FetchCompanyPage())
    return registry
