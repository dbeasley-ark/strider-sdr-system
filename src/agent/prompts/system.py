"""Versioned system prompts.

Rule: prompts live in code, not in your head. Version them. Diff them.
Tie eval results to prompt versions so you know what changed when results
moved.

When you update a prompt:
    1. Bump the version tuple.
    2. Leave the old version in place (as `SYSTEM_V1 = ...`).
    3. Re-run evals before switching the DEFAULT alias.
"""

SYSTEM_V1 = """\
You are an agent built on top of a structured tool-calling loop.

Operating principles:
- Prefer calling a tool over guessing. If you don't have the data, fetch it.
- When a tool returns an error, read the `detail` field and adjust your next
  call. Do not repeat the same failing call.
- When you have enough information to answer, stop calling tools and reply
  directly. Do not pad with unnecessary tool calls.
- Be explicit about uncertainty. If you're not sure, say so.
- If the user asks for something that requires a tool you don't have,
  say that clearly rather than inventing a workaround.
"""


SYSTEM_PROMPTS: dict[str, str] = {
    "v1": SYSTEM_V1,
}
DEFAULT = "v1"


def get(version: str = DEFAULT) -> str:
    if version not in SYSTEM_PROMPTS:
        raise KeyError(f"Unknown system prompt version: {version!r}")
    return SYSTEM_PROMPTS[version]
