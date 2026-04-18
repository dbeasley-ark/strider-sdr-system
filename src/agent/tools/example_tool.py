"""An example tool showing the contract in action.

DELETE THIS FILE when you build your real tools. It exists as a reference,
not as a dependency.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent.tools._base import Tool, ToolExecutionError


class _Input(BaseModel):
    user_id: str = Field(
        ...,
        description="The user's numeric ID, as a string. Must match ^[0-9]+$.",
        pattern=r"^[0-9]+$",
        examples=["12345", "7"],
    )
    fields: list[str] = Field(
        default_factory=lambda: ["name", "email"],
        description=(
            "Which user fields to return. Allowed: name, email, created_at. "
            "Omit for default set."
        ),
    )


class _Output(BaseModel):
    user_id: str
    name: str | None = None
    email: str | None = None
    created_at: str | None = None


class GetUser(Tool[_Input, _Output]):
    name = "get_user"
    description = (
        "Fetch basic profile information for a single user by their numeric ID. "
        "Use this when you need to look up a user's name or email before taking "
        "an action on their behalf. Does not return sensitive fields."
    )
    Input = _Input
    Output = _Output
    examples = [
        {"user_id": "12345", "fields": ["name", "email"]},
        {"user_id": "7"},
    ]
    idempotent = True
    side_effects: list[str] = []  # read-only

    async def run(self, inputs: _Input) -> _Output:
        # Replace with your real data source.
        fake_db = {
            "12345": {"name": "Ada Lovelace", "email": "ada@example.com", "created_at": "2024-01-15"},
            "7": {"name": "Alan Turing", "email": "alan@example.com", "created_at": "2023-06-23"},
        }
        record = fake_db.get(inputs.user_id)
        if record is None:
            # This is a normal business outcome, not an exception.
            # Let the LLM see it as data and decide what to do.
            raise ToolExecutionError(
                f"No user found with id {inputs.user_id}",
                retryable=False,
            )
        return _Output(
            user_id=inputs.user_id,
            **{k: v for k, v in record.items() if k in inputs.fields},
        )
