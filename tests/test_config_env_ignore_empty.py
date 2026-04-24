"""Regression: empty SAM_GOV_API_KEY in os.environ must not mask .env (pydantic-settings)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_env_ignore_empty_allows_dotenv_sam_over_empty_export(tmp_path: Path) -> None:
    """Docker / shells often export SAM_GOV_API_KEY= ; .env must still win."""
    repo_src = Path(__file__).resolve().parents[1] / "src"
    sam_key = "b" * 25
    ak = "sk-ant-api03-" + "x" * 40
    (tmp_path / ".env").write_text(
        f"ANTHROPIC_API_KEY={ak}\n"
        f"SAM_GOV_API_KEY={sam_key}\n"
        f"SAM_GOV_OPTIONAL=true\n"
        f"ARKENSTONE_AGENT_ENABLED=true\n",
        encoding="utf-8",
    )
    script = f"""import os, sys
sys.path.insert(0, {repr(str(repo_src))})
os.chdir({repr(str(tmp_path))})
os.environ["SAM_GOV_API_KEY"] = ""
os.environ["SAM_GOV_OPTIONAL"] = "true"
os.environ["ANTHROPIC_API_KEY"] = {repr(ak)}
os.environ.setdefault("ARKENSTONE_AGENT_ENABLED", "true")
import agent.config as cfg
v = cfg.settings.sam_gov_api_key.get_secret_value()
assert len(v) == 25 and v == {repr(sam_key)}, repr(v)
print("ok")
"""
    # Subprocess must not inherit tests/conftest.py skip flag (forces empty SAM).
    child_env = {k: v for k, v in os.environ.items() if k != "_AGENT_SKIP_STARTUP_CHECKS"}
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == "ok"
