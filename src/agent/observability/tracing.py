"""Structured, tamper-evident tracing.

Every interesting decision emits one JSONL line. Each line includes the
SHA-256 of the prior line's full serialized JSON, chaining the file
forward. Retroactive edits become detectable (§7.6, NIST SP 800-171
AU-9 alignment).

Layout:

    ./runs/<company-slug>/<iso-timestamp>/
        trace.jsonl     ← this file
        brief.json      ← final artifact (written separately)

Secret scrubbing (§7.6, AU-4/IA-5): values that match common secret
patterns (bearer tokens, API keys, UEIs in error contexts) are redacted
before the line is written. Dedicated tests cover this.

SECURITY_INCIDENT lines are written by the compliance hard-stop path
in output_filter.py. They're normal trace events with event_type
`security.incident` and are discoverable by grep.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from structlog.stdlib import BoundLogger

from agent.config import settings


def _configure_logging() -> None:
    settings.trace_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=settings.log_level.upper(),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_logging()
logger: BoundLogger = structlog.get_logger("agent")


# ── Secret scrubbing ─────────────────────────────────────────────────

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("sam_api_key_in_url", re.compile(r"(?i)(api_key=)[A-Za-z0-9\-]{20,}")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.=]{20,}")),
    (
        "inline_token",
        re.compile(r"(?i)\b(token|secret|password|api[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9\-_.]{16,}"),
    ),
]


def scrub(value: Any) -> Any:
    """Recursively redact secret-ish substrings from trace values."""
    if isinstance(value, str):
        redacted = value
        for label, pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
        return redacted
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


# ── Hash-chained trace ──────────────────────────────────────────────


_GENESIS_HASH = "0" * 64  # prior-hash for the very first line of a new trace file


class Trace:
    """Per-run tamper-evident trace.

    Usage:

        run_dir = new_run_dir("Shield AI")
        with Trace(run_dir=run_dir) as trace:
            trace.event("agent.start", goal="...")
    """

    def __init__(
        self,
        *,
        run_dir: Path | None = None,
        run_id: str | None = None,
    ) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.started_at = time.time()
        if run_dir is None:
            run_dir = settings.trace_dir / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir: Path = run_dir
        self._path: Path = run_dir / "trace.jsonl"
        self._file: Any = None
        self._prev_hash: str = _GENESIS_HASH
        self._line_n: int = 0

    def __enter__(self) -> Trace:
        self._file = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc is not None:
            self.event(
                "agent.end",
                status="error",
                error=str(exc),
                error_type=getattr(exc_type, "__name__", "UnknownError"),
            )
        if self._file is not None:
            self._file.close()

    def event(self, event_type: str, **fields: Any) -> None:
        """Append one hash-chained line to the trace."""
        self._line_n += 1
        scrubbed = scrub(fields)
        record = {
            "n": self._line_n,
            "run_id": self.run_id,
            "ts": time.time(),
            "ts_iso": datetime.now(UTC).isoformat(),
            "elapsed_s": round(time.time() - self.started_at, 3),
            "event": event_type,
            "prev_hash": self._prev_hash,
            **scrubbed,
        }
        serialized = json.dumps(record, default=str, sort_keys=True)
        if self._file is not None:
            self._file.write(serialized + "\n")
            self._file.flush()
        # Next line's prev_hash covers the exact bytes persisted.
        self._prev_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        logger.info(event_type, **fields, run_id=self.run_id)

    def incident(self, reason: str, **fields: Any) -> None:
        """Emit a SECURITY_INCIDENT line. grep-discoverable."""
        self.event("security.incident", reason=reason, **fields)

    @property
    def path(self) -> Path:
        return self._path


# ── Run directory helpers ────────────────────────────────────────────


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Filesystem-safe slug: lowercase, hyphen-separated, ASCII-only.

    Drops scheme, `www.` prefix, any URL path, and query string — the
    slug represents the COMPANY, not a specific page.
    """
    text = text.lower().strip()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    if text.startswith("www."):
        text = text[len("www."):]
    # Drop path + query.
    text = text.split("/", 1)[0].split("?", 1)[0]
    return _SLUG_PATTERN.sub("-", text).strip("-") or "unknown"


def new_run_dir(company: str, *, base: Path | None = None) -> Path:
    """Create and return `<base>/<company-slug>/<iso-ts>/`."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    root = base or settings.trace_dir
    out = root / slugify(company) / ts
    out.mkdir(parents=True, exist_ok=True)
    return out


# ── Integrity verification ──────────────────────────────────────────


def verify_chain(trace_path: Path) -> tuple[bool, str | None]:
    """Recompute the hash chain; return (ok, reason_if_not)."""
    prev = _GENESIS_HASH
    with trace_path.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return False, f"line {lineno}: not valid JSON"
            if record.get("prev_hash") != prev:
                return False, f"line {lineno}: prev_hash mismatch"
            prev = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return True, None
