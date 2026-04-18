"""Structured tracing.

Every interesting decision in the agent loop emits one line of JSONL.
This is your audit trail and your debugger. The rule: if you can't
reconstruct what happened from the trace, you're flying blind.

Emitted events (event_type):
    agent.start              – new run begins
    agent.end                – run complete (success or failure)
    llm.request              – before a Messages API call
    llm.response             – after; includes usage
    tool.call                – about to invoke a tool
    tool.result              – tool returned
    tool.error               – tool raised
    budget.exceeded          – a hard rail was hit
    halt.max_iterations      – loop halted for iteration count
    halt.human_escalation    – loop halted pending human input
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
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


class Trace:
    """A per-run trace that writes JSONL to disk.

    Usage:
        with Trace() as trace:
            trace.event("agent.start", goal=goal)
            ...
            trace.event("agent.end", status="ok")
    """

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.started_at = time.time()
        self._path: Path = settings.trace_dir / f"{self.run_id}.jsonl"
        self._file: Any = None

    def __enter__(self) -> Trace:
        self._file = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc is not None:
            self.event("agent.end", status="error", error=str(exc), error_type=exc_type.__name__)
        if self._file is not None:
            self._file.close()

    def event(self, event_type: str, **fields: Any) -> None:
        record = {
            "run_id": self.run_id,
            "ts": time.time(),
            "elapsed_s": round(time.time() - self.started_at, 3),
            "event": event_type,
            **fields,
        }
        if self._file is not None:
            self._file.write(json.dumps(record, default=str) + "\n")
            self._file.flush()
        logger.info(event_type, **fields, run_id=self.run_id)

    @property
    def path(self) -> Path:
        return self._path
