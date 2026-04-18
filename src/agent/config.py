"""Central configuration. All budgets and model settings flow through here.

Budgets are not suggestions — they're hard rails. The agent loop checks them
on every iteration and halts cleanly when any is exceeded.
"""

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(str, Enum):
    """Which ceremony level to run at. Set once, upgrade deliberately."""

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

    # ── API ──────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")

    # ── Model ────────────────────────────────────────────────────────
    model: str = "claude-opus-4-7"
    max_tokens: int = 8192

    # Extended thinking budget. Set to 0 to disable. For Opus 4.7, >=64k
    # is recommended for xhigh/max effort tasks.
    thinking_budget_tokens: int = 0

    # ── Budgets (hard rails) ─────────────────────────────────────────
    max_iterations: int = 25
    """Max agent loop iterations before forced halt."""

    max_cost_usd: float = 1.00
    """Max spend per task. Tracked via observability/cost.py."""

    max_wall_seconds: int = 300
    """Max wall-clock time per task."""

    # ── Observability ────────────────────────────────────────────────
    trace_dir: Path = Path("./traces")
    log_level: str = "INFO"

    # ── Profile ──────────────────────────────────────────────────────
    profile: Profile = Profile.STANDARD


settings = Settings()  # type: ignore[call-arg]
