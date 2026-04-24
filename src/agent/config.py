"""Central configuration.

Budgets are enforced by the agent loop; violations halt cleanly with a
structured `insufficient_data` brief. Required secrets and the kill
switch are validated at process start — fail loud, never half-run
(spec §7.5).
"""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(str, Enum):
    LEAN = "lean"
    STANDARD = "standard"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AGENT_",
        env_ignore_empty=True,
        extra="ignore",
    )

    enabled: bool = Field(default=True, alias="ARKENSTONE_AGENT_ENABLED")

    anthropic_api_key: SecretStr = Field(..., alias="ANTHROPIC_API_KEY")
    sam_gov_api_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""),
        alias="SAM_GOV_API_KEY",
    )
    # Empty SAM key ok at startup; SAM tool returns not_found until configured.
    sam_gov_optional: bool = Field(default=False, alias="SAM_GOV_OPTIONAL")

    model: str = "claude-opus-4-7"
    # Headroom for tool-heavy turns; too low → stop_reason=max_tokens.
    max_tokens: int = 8192
    thinking_adaptive: bool = True

    max_tool_calls: int = 13
    max_cost_usd: float = 0.50
    max_wall_seconds: int = 90
    # Per request input_tokens cap (web_search + tools often 50–80k).
    max_context_tokens: int = 128_000
    max_iterations: int = 20

    wall_reserve_seconds: int = 25  # One-time nudge when wall almost exhausted.
    wall_no_tools_buffer_seconds: int = 10  # Last N seconds: tools off; 0 disables.
    wall_synthesis_enabled: bool = True  # One tools-off call after hard wall.
    wall_synthesis_max_tokens: int = 4096

    runs_dir: Path = Field(default=Path("./runs"), alias="AGENT_RUNS_DIR")
    log_level: str = "INFO"

    @property
    def trace_dir(self) -> Path:
        """Back-compat alias; everything lives under the run dir."""
        return self.runs_dir

    profile: Profile = Profile.STANDARD

    user_agent: str = (
        "ArkenstoneProspectResearchBot/1.0 (+https://arkenstone.defense/bots)"
    )


class ConfigError(RuntimeError):
    """Raised when a required config value is missing or malformed at startup."""


_SAM_KEY_RE = re.compile(r"^[A-Za-z0-9\-]{20,}$")
_SAM_KEY_MIN_LEN = 20
_ANTHROPIC_KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,}$")


def _validate_startup(settings: Settings) -> None:
    if not settings.enabled:
        raise ConfigError(
            "Agent refuses to start: ARKENSTONE_AGENT_ENABLED is not 'true'. "
            "Set it explicitly in the environment to enable."
        )

    ak = settings.anthropic_api_key.get_secret_value()
    if not ak or not _ANTHROPIC_KEY_RE.match(ak):
        raise ConfigError(
            "ANTHROPIC_API_KEY is missing or malformed (expected 'sk-ant-...')."
        )

    # Unknown model slugs fail here (also keeps cost math aligned with PRICING_PER_MTOK).
    from agent.observability.cost import PRICING_PER_MTOK  # local import: avoid cycle

    if settings.model not in PRICING_PER_MTOK:
        known = ", ".join(sorted(PRICING_PER_MTOK))
        raise ConfigError(
            f"AGENT_MODEL={settings.model!r} is not a known Claude model slug. "
            f"Known slugs: {known}. "
            "If you recently updated Anthropic's catalog, add the new slug to "
            "PRICING_PER_MTOK in src/agent/observability/cost.py."
        )

    sk = settings.sam_gov_api_key.get_secret_value().strip()
    if settings.sam_gov_optional:
        if len(sk) >= _SAM_KEY_MIN_LEN and not _SAM_KEY_RE.match(sk):
            raise ConfigError(
                "SAM_GOV_API_KEY is set but malformed. Request one at "
                "https://open.gsa.gov/api/sam-api-key/ ."
            )
    elif not sk or not _SAM_KEY_RE.match(sk):
        raise ConfigError(
            "SAM_GOV_API_KEY is missing or malformed. Request one at "
            "https://open.gsa.gov/api/sam-api-key/ . "
            "For local runs without SAM yet, set SAM_GOV_OPTIONAL=true in .env."
        )


_env_enabled = os.environ.get("ARKENSTONE_AGENT_ENABLED")
if _env_enabled is not None and _env_enabled.strip().lower() in {"0", "false", "no"}:
    os.environ["ARKENSTONE_AGENT_ENABLED"] = "false"
else:
    os.environ.setdefault("ARKENSTONE_AGENT_ENABLED", "true")

# `_AGENT_SKIP_STARTUP_CHECKS=1` skips validation (imports without keys, --help).
if os.environ.get("_AGENT_SKIP_STARTUP_CHECKS") == "1":
    settings = Settings.model_construct(
        enabled=True,
        anthropic_api_key=SecretStr(""),
        sam_gov_api_key=SecretStr(""),
        model="claude-opus-4-7",
        wall_reserve_seconds=25,
        wall_no_tools_buffer_seconds=10,
        wall_synthesis_enabled=True,
        wall_synthesis_max_tokens=4096,
    )
else:
    settings = Settings()  # type: ignore[call-arg]
    _validate_startup(settings)
