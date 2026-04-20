"""Startup validation for SAM optional mode."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from agent.config import ConfigError, Settings, _validate_startup


def _settings(
    *,
    sam_key: str,
    sam_optional: bool,
) -> Settings:
    return Settings.model_construct(
        enabled=True,
        anthropic_api_key=SecretStr("sk-ant-api03-" + "x" * 40),
        sam_gov_api_key=SecretStr(sam_key),
        sam_gov_optional=sam_optional,
    )


def test_sam_optional_ignores_short_placeholder_key() -> None:
    """`SAM_GOV_API_KEY=...` with optional SAM must not crash startup."""
    _validate_startup(_settings(sam_key="...", sam_optional=True))


def test_sam_optional_still_rejects_long_malformed_key() -> None:
    with pytest.raises(ConfigError, match="SAM_GOV_API_KEY is set but malformed"):
        _validate_startup(
            _settings(sam_key="!" * 20, sam_optional=True),
        )
