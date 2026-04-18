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
        extra="ignore",
    )

    # ── Kill switch (§7.5) ────────────────────────────────────────────
    enabled: bool = Field(default=True, alias="ARKENSTONE_AGENT_ENABLED")

    # ── API keys (required) ──────────────────────────────────────────
    anthropic_api_key: SecretStr = Field(..., alias="ANTHROPIC_API_KEY")
    sam_gov_api_key: SecretStr = Field(..., alias="SAM_GOV_API_KEY")

    # ── Model ────────────────────────────────────────────────────────
    model: str = "claude-opus-4-7"
    max_tokens: int = 4096
    thinking_adaptive: bool = True

    # ── Budgets (hard rails — §1 + §6) ───────────────────────────────
    max_tool_calls: int = 12
    max_cost_usd: float = 0.50
    max_wall_seconds: int = 90
    max_context_tokens: int = 40_000
    max_iterations: int = 20

    # ── Observability ────────────────────────────────────────────────
    runs_dir: Path = Field(default=Path("./runs"), alias="AGENT_RUNS_DIR")
    log_level: str = "INFO"

    @property
    def trace_dir(self) -> Path:
        """Back-compat alias; everything lives under the run dir."""
        return self.runs_dir

    # ── Profile ──────────────────────────────────────────────────────
    profile: Profile = Profile.STANDARD

    # ── Tool posture (§4.1) ──────────────────────────────────────────
    user_agent: str = (
        "ArkenstoneProspectResearchBot/1.0 (+https://arkenstone.defense/bots)"
    )


class ConfigError(RuntimeError):
    """Raised when a required config value is missing or malformed at startup."""


_SAM_KEY_RE = re.compile(r"^[A-Za-z0-9\-]{20,}$")
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

    sk = settings.sam_gov_api_key.get_secret_value()
    if not sk or not _SAM_KEY_RE.match(sk):
        raise ConfigError(
            "SAM_GOV_API_KEY is missing or malformed. Request one at "
            "https://open.gsa.gov/api/sam-api-key/ ."
        )


# Normalize the kill switch to "true"/"false" so pydantic parses it predictably.
_env_enabled = os.environ.get("ARKENSTONE_AGENT_ENABLED")
if _env_enabled is not None and _env_enabled.strip().lower() in {"0", "false", "no"}:
    os.environ["ARKENSTONE_AGENT_ENABLED"] = "false"
else:
    os.environ.setdefault("ARKENSTONE_AGENT_ENABLED", "true")

# Short-circuit when the user is running `agent --help` or similar:
# only enforce startup validation when we actually need to run the agent.
# `_AGENT_SKIP_STARTUP_CHECKS=1` lets tooling import `config` without keys.
if os.environ.get("_AGENT_SKIP_STARTUP_CHECKS") == "1":
    settings = Settings.model_construct(
        enabled=True,
        anthropic_api_key=SecretStr(""),
        sam_gov_api_key=SecretStr(""),
    )
else:
    settings = Settings()  # type: ignore[call-arg]
    _validate_startup(settings)
