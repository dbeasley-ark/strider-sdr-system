"""Input validators.

First line of defense. These run *before* untrusted content reaches the LLM.
They are not a silver bullet — they catch the obvious. Your threat model
in AGENT_SPEC.md §7 should tell you what else you need.

Usage:
    validator = InputValidator()
    clean = validator.check(user_text, source="user_email")
    # raises InputRejected if the content fails checks
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class InputRejected(Exception):
    """Raised when a validator refuses input."""

    def __init__(self, reason: str, *, source: str) -> None:
        super().__init__(f"Input from {source!r} rejected: {reason}")
        self.reason = reason
        self.source = source


# Common prompt-injection patterns. Non-exhaustive — treat as a starting point,
# not a complete defense.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("instruction_override", re.compile(r"ignore (all |previous |prior )?(instructions|prompts|rules)", re.IGNORECASE)),
    ("system_impersonation", re.compile(r"\b(system|assistant)\s*[:]\s*", re.IGNORECASE)),
    ("role_injection", re.compile(r"<\|(system|user|assistant)\|>", re.IGNORECASE)),
    ("jailbreak_phrase", re.compile(r"(developer mode|dan mode|pretend you are)", re.IGNORECASE)),
    ("exfil_instruction", re.compile(r"(send|email|post|upload) .*(api.?key|secret|password|token)", re.IGNORECASE)),
]


@dataclass
class InputValidator:
    max_length: int = 50_000
    reject_injection_patterns: bool = True
    allow_urls: bool = True

    def check(self, text: str, *, source: str) -> str:
        """Validate `text` or raise InputRejected.

        Returns the (possibly normalized) text if it passes.
        """
        if len(text) > self.max_length:
            raise InputRejected(
                f"Exceeds max length ({len(text)} > {self.max_length})",
                source=source,
            )

        if self.reject_injection_patterns:
            for name, pattern in _INJECTION_PATTERNS:
                if pattern.search(text):
                    raise InputRejected(
                        f"Matched injection pattern: {name}",
                        source=source,
                    )

        if not self.allow_urls and re.search(r"https?://", text):
            raise InputRejected("URLs not permitted", source=source)

        return text.strip()
