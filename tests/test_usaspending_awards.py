"""USAspending tool: contract / IDV group fan-out.

The API rejects `award_type_codes` that mixes the `contracts` group with
the `idv` group (422 "must only contain types from one group"). The tool
fans out one POST per requested group and merges results; these tests
cover the happy path (both groups succeed, dedupe by Award ID), the
partial-failure path (one group errors, the other returns rows), and the
full-failure path (both groups error — surfaced in `error`).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.reliability import TransientError
from agent.tools import lookup_usaspending_awards as mod


class _FakePost:
    """Stand-in for `_usaspending_post` that routes by award_type_codes group."""

    def __init__(self, by_group: dict[str, Any]) -> None:
        self.by_group = by_group
        self.calls: list[list[str]] = []

    async def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        codes = list(body["filters"]["award_type_codes"])
        self.calls.append(codes)
        group = "idv" if any(c.startswith("IDV_") for c in codes) else "contract"
        outcome = self.by_group.get(group)
        if isinstance(outcome, BaseException):
            raise outcome
        assert outcome is not None, f"test did not wire outcome for {group=}"
        return outcome


def _award_row(award_id: str, amount: float, award_type: str = "D") -> dict[str, Any]:
    return {
        "Award ID": award_id,
        "Recipient Name": "Test Corp",
        "Awarding Agency": "DOD",
        "Awarding Sub Agency": None,
        "Award Amount": amount,
        "Start Date": "2024-01-01",
        "End Date": "2025-01-01",
        "Description": "x" * 10,
        "NAICS": {"code": "541511", "description": "Programming"},
        "generated_internal_id": f"gid_{award_id}",
        "award_type": award_type,
    }


@pytest.mark.asyncio
async def test_fans_out_one_post_per_group(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePost(
        by_group={
            "contract": {
                "results": [_award_row("C1", 10.0, "D"), _award_row("C2", 5.0, "D")],
                "page_metadata": {"total": 2},
            },
            "idv": {
                "results": [_award_row("I1", 3.0, "IDV_A")],
                "page_metadata": {"total": 1},
            },
        },
    )
    monkeypatch.setattr(mod, "_usaspending_post", fake)

    tool = mod.LookupUSAspendingAwards()
    result = await tool({"recipient_name": "Test Corp"})

    # One POST per group (not a single merged POST with mixed codes).
    assert len(fake.calls) == 2
    groups_seen = {tuple(c) for c in fake.calls}
    assert ("A", "B", "C", "D") in groups_seen
    assert ("IDV_A", "IDV_B", "IDV_C") in groups_seen

    assert result["error"] is None
    assert result["total_awards_found"] == 3
    assert len(result["awards"]) == 3
    # Sorted desc by amount, dedup'd by Award ID.
    assert [a["award_id"] for a in result["awards"]] == ["C1", "C2", "I1"]


@pytest.mark.asyncio
async def test_single_group_request_sends_single_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePost(
        by_group={
            "contract": {
                "results": [_award_row("C1", 10.0, "D")],
                "page_metadata": {"total": 1},
            },
        },
    )
    monkeypatch.setattr(mod, "_usaspending_post", fake)

    tool = mod.LookupUSAspendingAwards()
    result = await tool(
        {"recipient_name": "Test Corp", "award_types": ["contract"]},
    )
    assert len(fake.calls) == 1
    assert fake.calls[0] == ["A", "B", "C", "D"]
    assert result["error"] is None
    assert len(result["awards"]) == 1


@pytest.mark.asyncio
async def test_one_group_errors_other_succeeds_returns_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePost(
        by_group={
            "contract": {
                "results": [_award_row("C1", 10.0, "D")],
                "page_metadata": {"total": 1},
            },
            "idv": TransientError("USAspending 503"),
        },
    )
    monkeypatch.setattr(mod, "_usaspending_post", fake)

    tool = mod.LookupUSAspendingAwards()
    result = await tool({"recipient_name": "Test Corp"})

    assert len(result["awards"]) == 1
    assert result["awards"][0]["award_id"] == "C1"
    # Partial error surfaces so the agent knows the IDV leg didn't run.
    assert result["error"] and "idv" in result["error"]


@pytest.mark.asyncio
async def test_both_groups_error_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePost(
        by_group={
            "contract": TransientError("USAspending 503"),
            "idv": TransientError("USAspending 503"),
        },
    )
    monkeypatch.setattr(mod, "_usaspending_post", fake)

    tool = mod.LookupUSAspendingAwards()
    result = await tool({"recipient_name": "Test Corp"})

    assert result["awards"] == []
    assert result["error"] and "contract" in result["error"] and "idv" in result["error"]
