"""Tests for sales UI subprocess env (repo .env must win over empty exports)."""

from __future__ import annotations

import os
from pathlib import Path

from agent.sales_app import _merge_repo_dotenv


def test_merge_repo_dotenv_overrides_empty_exported_key(tmp_path: Path) -> None:
    key = "a" * 25  # meets SAM-style length used elsewhere
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"SAM_GOV_API_KEY={key}\n", encoding="utf-8")
    base = dict(os.environ)
    base["SAM_GOV_API_KEY"] = ""
    out = _merge_repo_dotenv(base, dotenv_path=dotenv)
    assert out["SAM_GOV_API_KEY"] == key


def test_merge_repo_dotenv_skips_missing_file(tmp_path: Path) -> None:
    base = {"X": "1"}
    out = _merge_repo_dotenv(base, dotenv_path=tmp_path / "nope.env")
    assert out == base
