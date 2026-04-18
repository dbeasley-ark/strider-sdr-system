"""Pytest configuration: skip the config startup validation.

Tests exercise modules that import `agent.config`, which normally
refuses to load without ANTHROPIC_API_KEY and SAM_GOV_API_KEY. Set
a skip-flag before imports so test runs don't require production
secrets.
"""

import os

os.environ.setdefault("_AGENT_SKIP_STARTUP_CHECKS", "1")
