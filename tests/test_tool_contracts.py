"""Tests for tool contract enforcement.

These tests are how you know the contract discipline is real. If any of
them pass when they shouldn't, the contract has a hole.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from agent.tools._base import Tool, ToolContractError, ToolExecutionError


class _GoodInput(BaseModel):
    x: int = Field(..., description="An integer.")


class _GoodOutput(BaseModel):
    doubled: int


class GoodTool(Tool[_GoodInput, _GoodOutput]):
    name = "good_tool"
    description = "Doubles an integer. Use when the caller wants x * 2."
    Input = _GoodInput
    Output = _GoodOutput
    examples = [{"x": 3}, {"x": 0}]

    async def run(self, inputs: _GoodInput) -> _GoodOutput:
        return _GoodOutput(doubled=inputs.x * 2)


def test_good_tool_registers() -> None:
    """Sanity check: a compliant tool works."""
    tool = GoodTool()
    assert tool.name == "good_tool"


def test_missing_description_raises() -> None:
    class _I(BaseModel):
        x: int = Field(..., description="x.")

    class _O(BaseModel):
        y: int

    with pytest.raises(ToolContractError, match="too terse|missing required"):
        class _Bad(Tool[_I, _O]):
            name = "bad"
            description = "too short"  # under 20 chars
            Input = _I
            Output = _O
            examples = [{"x": 1}]

            async def run(self, inputs: _I) -> _O:
                return _O(y=inputs.x)


def test_missing_field_description_raises() -> None:
    class _I(BaseModel):
        x: int  # no description

    class _O(BaseModel):
        y: int

    with pytest.raises(ToolContractError, match="no description"):
        class _Bad(Tool[_I, _O]):
            name = "bad"
            description = "A tool with a vague input field that should fail."
            Input = _I
            Output = _O
            examples = [{"x": 1}]

            async def run(self, inputs: _I) -> _O:
                return _O(y=inputs.x)


def test_missing_examples_raises() -> None:
    class _I(BaseModel):
        x: int = Field(..., description="x.")

    class _O(BaseModel):
        y: int

    with pytest.raises(ToolContractError, match="examples"):
        class _Bad(Tool[_I, _O]):
            name = "bad"
            description = "A tool without any examples — the contract forbids."
            Input = _I
            Output = _O
            examples = []  # empty

            async def run(self, inputs: _I) -> _O:
                return _O(y=inputs.x)


def test_bad_example_schema_raises() -> None:
    class _I(BaseModel):
        x: int = Field(..., description="x.")

    class _O(BaseModel):
        y: int

    with pytest.raises(ToolContractError, match="does not match Input schema"):
        class _Bad(Tool[_I, _O]):
            name = "bad"
            description = "A tool whose example does not match its schema."
            Input = _I
            Output = _O
            examples = [{"x": "not an int"}]

            async def run(self, inputs: _I) -> _O:
                return _O(y=inputs.x)


def test_non_snake_case_name_raises() -> None:
    class _I(BaseModel):
        x: int = Field(..., description="x.")

    class _O(BaseModel):
        y: int

    with pytest.raises(ToolContractError, match="snake_case"):
        class _Bad(Tool[_I, _O]):
            name = "BadName"
            description = "A tool with a non-snake-case name should be rejected."
            Input = _I
            Output = _O
            examples = [{"x": 1}]

            async def run(self, inputs: _I) -> _O:
                return _O(y=inputs.x)


@pytest.mark.asyncio
async def test_invalid_input_returns_structured_error() -> None:
    tool = GoodTool()
    result = await tool({"x": "not an int"})
    assert result["error"] == "input_validation_failed"
    assert "detail" in result


@pytest.mark.asyncio
async def test_valid_input_returns_output() -> None:
    tool = GoodTool()
    result = await tool({"x": 5})
    assert result == {"doubled": 10}


@pytest.mark.asyncio
async def test_tool_execution_error_surfaces() -> None:
    class _Raiser(Tool[_GoodInput, _GoodOutput]):
        name = "raiser"
        description = "A tool that always raises a tool execution error."
        Input = _GoodInput
        Output = _GoodOutput
        examples = [{"x": 1}]

        async def run(self, inputs: _GoodInput) -> _GoodOutput:
            raise ToolExecutionError("nope", retryable=False)

    tool = _Raiser()
    result = await tool({"x": 1})
    assert result["error"] == "tool_execution_failed"
    assert result["retryable"] is False
