"""Demo entry point. Run: `python -m agent`

Wires up the example tool and sends a trivial goal through the loop.
This is a smoke test — replace with your own entry points.
"""

from __future__ import annotations

import asyncio

from rich import print

from agent.agent import Agent
from agent.security.permissions import PermissionScope
from agent.tools import ToolRegistry
from agent.tools.example_tool import GetUser


async def main() -> None:
    registry = ToolRegistry()
    registry.register(GetUser())

    scope = PermissionScope(name="demo", allow_list={"get_user"})

    agent = Agent(registry=registry, scope=scope)
    result = await agent.run("What is the email address for user 12345?")

    print("\n[bold]=== RESULT ===[/bold]")
    print(f"status:       {result.status}")
    print(f"iterations:   {result.iterations}")
    print(f"wall time:    {result.wall_seconds}s")
    print(f"cost:         ${result.cost_usd}")
    print(f"trace:        {result.trace_path}")
    print(f"\n[bold]output:[/bold]\n{result.output}")
    if result.error:
        print(f"\n[red]error:[/red] {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
