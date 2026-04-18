"""Tool contract base. This is the heart of contract discipline.

Every tool in this template MUST:
    1. Define a Pydantic Input model with field descriptions.
    2. Define a Pydantic Output model.
    3. Provide at least one input example (Tool Use Example pattern).
    4. Have an unambiguous, action-oriented description.

These aren't suggestions. The registry rejects tools that don't meet them.
The point is to remove ambiguity so the LLM can't "imagine" what your
tool accepts.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ValidationError

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class ToolContractError(Exception):
    """Raised when a tool is defined without meeting the contract requirements."""


class ToolExecutionError(Exception):
    """Raised when a tool fails at runtime in a way the LLM should see."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class Tool(ABC, Generic[TInput, TOutput]):
    """Base class for all tools.

    Subclasses must define:
        name         – snake_case identifier used by Claude.
        description  – what the tool does and when to use it.
        Input        – Pydantic model for inputs.
        Output       – Pydantic model for outputs.
        examples     – at least one concrete input example.
        run()        – the actual implementation.

    Optional:
        idempotent   – if False, the registry may refuse unsafe retries.
        side_effects – human-readable list for the threat model.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    Input: ClassVar[type[BaseModel]]
    Output: ClassVar[type[BaseModel]]
    examples: ClassVar[list[dict[str, Any]]] = []
    idempotent: ClassVar[bool] = True
    side_effects: ClassVar[list[str]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Skip abstract intermediate bases
        if inspect.isabstract(cls):
            return
        cls._validate_contract()

    @classmethod
    def _validate_contract(cls) -> None:
        """Fail loudly at import time if a tool violates the contract."""
        missing: list[str] = []
        for attr in ("name", "description", "Input", "Output"):
            if not hasattr(cls, attr) or getattr(cls, attr) in (None, ""):
                missing.append(attr)
        if missing:
            raise ToolContractError(
                f"{cls.__name__} is missing required attributes: {missing}"
            )

        if not cls.name.isidentifier() or not cls.name.islower():
            raise ToolContractError(
                f"{cls.__name__}.name must be snake_case; got {cls.name!r}"
            )

        if len(cls.description) < 20:
            raise ToolContractError(
                f"{cls.__name__}.description is too terse "
                f"({len(cls.description)} chars). LLMs need explicit guidance on "
                f"when and how to use this tool."
            )

        if not issubclass(cls.Input, BaseModel) or not issubclass(
            cls.Output, BaseModel
        ):
            raise ToolContractError(
                f"{cls.__name__}.Input and .Output must be Pydantic BaseModels"
            )

        # Every Input field must have a description — no bare `str` or `int`.
        for field_name, field in cls.Input.model_fields.items():
            if not field.description:
                raise ToolContractError(
                    f"{cls.__name__}.Input.{field_name} has no description. "
                    f"Add Field(..., description='...') to make the contract "
                    f"explicit."
                )

        if not cls.examples:
            raise ToolContractError(
                f"{cls.__name__} has no examples. Add at least one concrete "
                f"example input to .examples — this is the Tool Use Example "
                f"pattern and it measurably reduces parameter errors."
            )

        # Validate that each example actually parses against the Input schema.
        for i, ex in enumerate(cls.examples):
            try:
                cls.Input.model_validate(ex)
            except ValidationError as e:
                raise ToolContractError(
                    f"{cls.__name__}.examples[{i}] does not match Input schema: {e}"
                ) from e

    # ── Execution ────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, inputs: TInput) -> TOutput:
        """The actual tool logic. Implement this."""

    async def __call__(self, raw_inputs: dict[str, Any]) -> dict[str, Any]:
        """Entry point used by the agent loop.

        Validates inputs, executes, validates outputs, returns a dict safe
        to pass back to the LLM. Errors are caught and returned as a
        structured error payload so the LLM can see them and decide what to do.
        """
        try:
            parsed = self.Input.model_validate(raw_inputs)
        except ValidationError as e:
            return {
                "error": "input_validation_failed",
                "detail": e.errors(include_url=False),
            }

        try:
            result = await self.run(parsed)  # type: ignore[arg-type]
        except ToolExecutionError as e:
            return {
                "error": "tool_execution_failed",
                "detail": str(e),
                "retryable": e.retryable,
            }

        try:
            validated = self.Output.model_validate(result.model_dump())
        except ValidationError as e:
            # This is a bug in the tool, not in the LLM — surface clearly.
            return {
                "error": "output_schema_violation",
                "detail": e.errors(include_url=False),
            }

        return validated.model_dump(mode="json")

    # ── Schema export for Anthropic API ──────────────────────────────

    @classmethod
    def to_anthropic_schema(cls) -> dict[str, Any]:
        """Convert to the shape expected by Anthropic's tool-use API."""
        json_schema = cls.Input.model_json_schema()
        # Strip Pydantic-specific $defs if they'd confuse the LLM; here we
        # keep them because Claude handles nested refs fine.
        return {
            "name": cls.name,
            "description": cls.description,
            "input_schema": json_schema,
        }
