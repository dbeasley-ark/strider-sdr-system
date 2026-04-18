"""Tool registry. Collects all tools and hands them to the agent.

Two modes:
    inline  – all schemas sent in every request. Use when you have <20 tools.
    search  – only a search_tools tool is sent; the LLM discovers tools
              on demand. Use when you have 20+ tools (reduces context by ~85%).
"""

from __future__ import annotations

from typing import Any

from agent.tools._base import Tool


class ToolRegistry:
    """A container for Tool subclasses that the agent can call."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Tool {tool.name!r} already registered. Tool names must be unique."
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name!r}")
        return self._tools[name]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # ── Export for the API ───────────────────────────────────────────

    def to_anthropic_schemas(self) -> list[dict[str, Any]]:
        """Inline mode: return all tool schemas."""
        return [type(t).to_anthropic_schema() for t in self._tools.values()]

    def to_search_schema(self) -> list[dict[str, Any]]:
        """Search mode: return a single search_tools tool.

        The LLM calls search_tools(query=...) and gets back matching tool
        schemas, which it then uses in subsequent turns. Use when len(registry)
        is large enough that inline schemas bloat the context.

        NOTE: This is a scaffold. For production, wire this up to a semantic
        search over tool descriptions or use the native Tool Search Tool
        feature on the API.
        """
        return [
            {
                "name": "search_tools",
                "description": (
                    "Search for tools by natural-language query. Returns a list "
                    "of matching tool schemas. Use this when you need a capability "
                    "you haven't seen yet."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What the tool should do, in natural language.",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 5,
                            "description": "Max number of tools to return.",
                        },
                    },
                    "required": ["query"],
                },
            }
        ]

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Stub lexical search. Replace with embeddings for real use."""
        q = query.lower()
        scored: list[tuple[int, Tool]] = []
        for tool in self._tools.values():
            haystack = f"{tool.name} {tool.description}".lower()
            score = sum(1 for word in q.split() if word in haystack)
            if score > 0:
                scored.append((score, tool))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [type(t).to_anthropic_schema() for _, t in scored[:limit]]
