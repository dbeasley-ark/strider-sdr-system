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

    # ── API keys ───────────────────────────────────────────────────────
    anthropic_api_key: SecretStr = Field(..., alias="ANTHROPIC_API_KEY")
    sam_gov_api_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""),
        alias="SAM_GOV_API_KEY",
    )
    # When true, an empty SAM key is allowed at startup; SAM lookups return
    # not_found so the model can lean on web_search until a key is issued.
    sam_gov_optional: bool = Field(default=False, alias="SAM_GOV_OPTIONAL")

    # ── Model ────────────────────────────────────────────────────────
    model: str = "claude-opus-4-7"
    # Tool-heavy turns (and adaptive thinking) need headroom; if this is too low
    # the API returns stop_reason=max_tokens and the run halts.
    max_tokens: int = 8192
    thinking_adaptive: bool = True

    # ── Budgets (hard rails — §1 + §6) ───────────────────────────────
    max_tool_calls: int = 13
    max_cost_usd: float = 0.50
    max_wall_seconds: int = 90
    # Per API request (usage.input_tokens). Web search + tool payloads often land
    # in the 50–80k range; 40k was halting otherwise-successful runs.
    max_context_tokens: int = 128_000
    max_iterations: int = 20

    # ── Wall clock: reserve + post-wall synthesis ─────────────────────
    # When remaining wall < reserve, inject a one-time user nudge to finalize.
    wall_reserve_seconds: int = 25
    # In the last N seconds of wall budget, disable tools (force JSON soon).
    # Set to 0 to disable.
    wall_no_tools_buffer_seconds: int = 10
    # After max_wall_seconds, one tools-off LLM call to turn trace into a Brief.
    wall_synthesis_enabled: bool = True
    wall_synthesis_max_tokens: int = 4096

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

    # Guard against stale/typo'd model slugs. The 19:55 UTC batch failed every
    # run with `model: claude-sonnet-4-7` (doesn't exist); fail loud at startup
    # instead of burning an iteration per row. PRICING_PER_MTOK is also the
    # cost-budget source-of-truth, so keeping them aligned avoids silent fallback
    # to Opus pricing for an unknown model.
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
        # Optional SAM: empty is fine. Short values (e.g. `...` from .env.example)
        # are treated as unset so copy-paste setups do not fail startup.
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
        model="claude-opus-4-7",
        wall_reserve_seconds=25,
        wall_no_tools_buffer_seconds=10,
        wall_synthesis_enabled=True,
        wall_synthesis_max_tokens=4096,
    )
else:
    settings = Settings()  # type: ignore[call-arg]
    _validate_startup(settings)
