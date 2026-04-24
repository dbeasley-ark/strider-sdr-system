"""Sales batch UI API: spreadsheet upload and sequential prospect-research runs.

Runs `python -m agent` in a subprocess per row so the API process never
imports agent.config (which requires API keys at import time).

Run from the repository root after `pip install -e ".[ui]"`:

    uv run prospect-sales-ui

Serve the static React app from `sales-ui/dist` in production, or run
`npm run dev` in `sales-ui/` with Vite proxying `/api` to this server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import re
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from dotenv import dotenv_values, load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.spreadsheet_import import ParsedSheet, SpreadsheetParseError, parse_prospect_spreadsheet

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


REPO_ROOT = _repo_root()


def domain_hint_from_website(s: str | None) -> str | None:
    """Turn a rep-pasted website or URL into a domain hint for ``--domain``."""
    if s is None:
        return None
    t = s.strip()
    if not t:
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", t):
        t = "https://" + t
    parsed = urlparse(t)
    host = (parsed.netloc or "").strip().lower()
    if not host and parsed.path:
        host = parsed.path.split("/", 1)[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host or None


def _pythonpath_for_subprocess() -> dict[str, str]:
    env = dict(os.environ)
    src = REPO_ROOT / "src"
    if src.is_dir():
        prev = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src) + (os.pathsep + prev if prev else "")
    return env


def _merge_repo_dotenv(env: dict[str, str], *, dotenv_path: Path) -> dict[str, str]:
    """Overlay ``.env`` onto ``env`` so the file wins (including over empty exports).

    The agent subprocess inherits ``os.environ``. An empty ``SAM_GOV_API_KEY=``
    from the parent or container often blocks pydantic-settings from using the
    real value in ``.env``. Merging here keeps single-run / batch runs aligned
    with the repo root ``.env`` without requiring a UI server restart after edits.
    """
    if not dotenv_path.is_file():
        return env
    merged = dict(env)
    for k, v in dotenv_values(dotenv_path).items():
        if v is None:
            continue
        merged[str(k)] = str(v)
    return merged


def _agent_subprocess_env() -> dict[str, str]:
    """Environment for ``python -m agent`` child processes (PYTHONPATH + root ``.env``)."""
    return _merge_repo_dotenv(
        _pythonpath_for_subprocess(),
        dotenv_path=REPO_ROOT / ".env",
    )


@dataclass
class RowResult:
    index: int
    company: str
    domain: str | None
    status: str  # pending | running | ok | error
    exit_code: int | None = None
    brief: dict[str, Any] | None = None
    run_dir: str | None = None
    error: str | None = None
    poc_name: str | None = None
    poc_title: str | None = None


@dataclass
class BatchJob:
    job_id: str
    filename: str
    parsed: ParsedSheet
    rows: list[RowResult] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    row_poc: list[tuple[str | None, str | None]] | None = None

    def __post_init__(self) -> None:
        if not self.rows:
            n = len(self.parsed.rows)
            pairs = self.row_poc if self.row_poc is not None else [(None, None)] * n
            if len(pairs) != n:
                raise ValueError(
                    f"row_poc length {len(pairs)} does not match parsed.rows length {n}"
                )
            self.rows = [
                RowResult(
                    index=i,
                    company=c,
                    domain=d,
                    status="pending",
                    poc_name=pn,
                    poc_title=pt,
                )
                for i, ((c, d), (pn, pt)) in enumerate(
                    zip(self.parsed.rows, pairs, strict=True)
                )
            ]


JOBS: dict[str, BatchJob] = {}
JOBS_LOCK = asyncio.Lock()


class SingleRunRequest(BaseModel):
    company: str = Field(min_length=1)
    website: str | None = None
    poc_name: str | None = None
    poc_title: str | None = None


# Agent CLI: 0 ok, 1 halted/insufficient, 2 error/compliance — all may print a Brief.
_AGENT_OK_EXIT_CODES = frozenset({0, 1, 2})


def _try_parse_brief_stdout(stdout_text: str) -> dict[str, Any] | None:
    """Parse a Brief-shaped dict from agent stdout.

    The agent prints one JSON object; tolerate leading noise (e.g. log lines)
    by scanning for ``{`` and using ``json.JSONDecoder.raw_decode``.
    """
    s = stdout_text.strip()
    if not s:
        return None
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []

    def _looks_like_brief(obj: dict[str, Any]) -> bool:
        return "verdict" in obj and (
            "federal_revenue_posture" in obj or "track" in obj
        )

    try:
        head = json.loads(s)
        if isinstance(head, dict) and _looks_like_brief(head):
            return head
    except json.JSONDecodeError:
        pass

    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(s, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and _looks_like_brief(obj):
            candidates.append(obj)
    return candidates[-1] if candidates else None


async def _append_event(job: BatchJob, event: dict[str, Any]) -> None:
    async with job.lock:
        job.events.append(event)


async def _run_batch(job_id: str) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    await _append_event(
        job,
        {
            "type": "job_started",
            "job_id": job_id,
            "total": len(job.rows),
            "filename": job.filename,
        },
    )

    env = _agent_subprocess_env()

    for row in job.rows:
        row.status = "running"
        await _append_event(
            job,
            {
                "type": "row_started",
                "index": row.index,
                "company": row.company,
                "domain": row.domain,
            },
        )

        cmd = [
            sys.executable,
            "-m",
            "agent",
            "--company",
            row.company,
            "--json",
        ]
        if row.domain:
            cmd.extend(["--domain", row.domain])
        if row.poc_name:
            cmd.extend(["--poc-name", row.poc_name])
        if row.poc_title:
            cmd.extend(["--poc-title", row.poc_title])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(REPO_ROOT),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await proc.communicate()
        except Exception as e:
            row.status = "error"
            row.error = str(e)
            row.exit_code = None
            await _append_event(
                job,
                {
                    "type": "row_complete",
                    "index": row.index,
                    "company": row.company,
                    "domain": row.domain,
                    "status": "error",
                    "error": str(e),
                },
            )
            continue

        stderr_text = stderr_b.decode("utf-8", errors="replace").strip()
        stdout_text = stdout_b.decode("utf-8", errors="replace").strip()
        run_dir_m = re.search(r"run dir:\s+(\S+)", stderr_text, re.IGNORECASE)
        brief = _try_parse_brief_stdout(stdout_text)

        if brief is not None:
            row.status = "ok"
            row.exit_code = proc.returncode
            row.brief = brief
            row.run_dir = run_dir_m.group(1) if run_dir_m else None
            await _append_event(
                job,
                {
                    "type": "row_complete",
                    "index": row.index,
                    "company": row.company,
                    "domain": row.domain,
                    "status": "ok",
                    "exit_code": proc.returncode,
                    "federal_revenue_posture": brief.get("federal_revenue_posture")
                    or brief.get("track"),
                    "verdict": brief.get("verdict"),
                    "brief": brief,
                },
            )
            continue

        if proc.returncode not in _AGENT_OK_EXIT_CODES:
            row.status = "error"
            row.exit_code = proc.returncode
            row.error = stderr_text or f"exit {proc.returncode}"
            await _append_event(
                job,
                {
                    "type": "row_complete",
                    "index": row.index,
                    "company": row.company,
                    "domain": row.domain,
                    "status": "error",
                    "exit_code": proc.returncode,
                    "error": row.error,
                },
            )
            continue

        hint = stderr_text[-1200:] if stderr_text else "(no stderr)"
        if not stdout_text:
            row.error = (
                "Agent produced no stdout (empty). The subprocess may have crashed "
                "before printing the brief. Stderr tail:\n"
                f"{hint}"
            )
        else:
            try:
                json.loads(stdout_text)
                row.error = (
                    "Agent stdout was JSON but not a prospect brief "
                    "(expected federal_revenue_posture + verdict). Stderr tail:\n"
                    f"{hint}"
                )
            except json.JSONDecodeError:
                row.error = (
                    "Agent stdout was not valid JSON (brief may be buried in log noise). "
                    "Stderr tail:\n"
                    f"{hint}"
                )

        row.status = "error"
        row.exit_code = proc.returncode
        await _append_event(
            job,
            {
                "type": "row_complete",
                "index": row.index,
                "company": row.company,
                "domain": row.domain,
                "status": "error",
                "exit_code": proc.returncode,
                "error": row.error,
            },
        )

    job.finished = True
    summary = {
        "type": "job_complete",
        "job_id": job_id,
        "ok": sum(1 for r in job.rows if r.status == "ok"),
        "error": sum(1 for r in job.rows if r.status == "error"),
    }
    await _append_event(job, summary)


def create_app() -> FastAPI:
    load_dotenv(REPO_ROOT / ".env")
    app = FastAPI(title="Prospect research — sales batch", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/batches")
    async def post_batch(
        background_tasks: BackgroundTasks,
        file: Annotated[UploadFile, File()],
        company_column: Annotated[str | None, Form()] = None,
        domain_column: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        raw = await file.read()
        if not raw:
            name = file.filename or "upload"
            logger.warning("batch upload rejected: empty file (%r)", name)
            raise HTTPException(status_code=400, detail="Empty file.")
        name = file.filename or "upload.csv"
        try:
            parsed = parse_prospect_spreadsheet(
                raw,
                filename=name,
                company_column=company_column,
                domain_column=domain_column,
            )
        except SpreadsheetParseError as e:
            logger.warning("batch upload rejected: %s (%r)", e, name)
            raise HTTPException(status_code=400, detail=str(e)) from e

        job_id = str(uuid.uuid4())
        job = BatchJob(job_id=job_id, filename=name, parsed=parsed)
        async with JOBS_LOCK:
            JOBS[job_id] = job

        background_tasks.add_task(_run_batch, job_id)

        return {
            "job_id": job_id,
            "filename": name,
            "row_count": len(parsed.rows),
            "headers": parsed.headers,
            "company_column_index": parsed.company_column,
            "domain_column_index": parsed.domain_column,
            "rows": [
                {"index": i, "company": c, "domain": d}
                for i, (c, d) in enumerate(parsed.rows)
            ],
        }

    @app.post("/api/single")
    async def post_single(
        background_tasks: BackgroundTasks,
        body: SingleRunRequest,
    ) -> dict[str, Any]:
        company = body.company.strip()
        if not company:
            raise HTTPException(status_code=400, detail="company is required.")
        domain = domain_hint_from_website(body.website)
        poc_name = (
            body.poc_name.strip()
            if body.poc_name and body.poc_name.strip()
            else None
        )
        poc_title = (
            body.poc_title.strip()
            if body.poc_title and body.poc_title.strip()
            else None
        )

        if domain:
            parsed = ParsedSheet(
                headers=["Company", "Domain"],
                company_column=0,
                domain_column=1,
                rows=[(company, domain)],
            )
        else:
            parsed = ParsedSheet(
                headers=["Company"],
                company_column=0,
                domain_column=None,
                rows=[(company, None)],
            )

        job_id = str(uuid.uuid4())
        job = BatchJob(
            job_id=job_id,
            filename="single-run",
            parsed=parsed,
            row_poc=[(poc_name, poc_title)],
        )
        async with JOBS_LOCK:
            JOBS[job_id] = job

        background_tasks.add_task(_run_batch, job_id)

        return {
            "job_id": job_id,
            "filename": job.filename,
            "row_count": len(parsed.rows),
            "headers": parsed.headers,
            "company_column_index": parsed.company_column,
            "domain_column_index": parsed.domain_column,
            "rows": [
                {"index": i, "company": c, "domain": d}
                for i, (c, d) in enumerate(parsed.rows)
            ],
        }

    @app.get("/api/batches/{job_id}")
    async def get_batch(job_id: str) -> dict[str, Any]:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Unknown job_id.")
        return _job_snapshot(job)

    @app.get("/api/batches/{job_id}/stream")
    async def stream_batch(job_id: str) -> StreamingResponse:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Unknown job_id.")

        async def gen() -> AsyncIterator[str]:
            """Stream job events as SSE.

            Emit periodic comment lines while waiting so proxies and browsers do not
            treat the connection as idle during long per-row agent runs (no events for
            minutes otherwise → common ~60s idle disconnect).
            """
            idx = 0
            idle_since = time.monotonic()
            ping_interval_s = 15.0
            while True:
                async with job.lock:
                    while idx < len(job.events):
                        line = json.dumps(job.events[idx], default=str)
                        idx += 1
                        yield f"data: {line}\n\n"
                        idle_since = time.monotonic()
                    done = job.finished and idx >= len(job.events)
                if done:
                    break
                await asyncio.sleep(0.2)
                if time.monotonic() - idle_since >= ping_interval_s:
                    yield ": ping\n\n"
                    idle_since = time.monotonic()

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    ui_dist = REPO_ROOT / "sales-ui" / "dist"
    if ui_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")

    return app


app = create_app()


def _job_snapshot(job: BatchJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "filename": job.filename,
        "finished": job.finished,
        "headers": job.parsed.headers,
        "rows": [
            {
                "index": r.index,
                "company": r.company,
                "domain": r.domain,
                "status": r.status,
                "exit_code": r.exit_code,
                "error": r.error,
                "federal_revenue_posture": (r.brief or {}).get("federal_revenue_posture")
                or (r.brief or {}).get("track"),
                "verdict": (r.brief or {}).get("verdict"),
                "brief": r.brief,
                "run_dir": r.run_dir,
            }
            for r in job.rows
        ],
    }


def main() -> None:
    import uvicorn

    host = os.environ.get("AGENT_SALES_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("AGENT_SALES_UI_PORT", "8765"))
    uvicorn.run(
        "agent.sales_app:app",
        host=host,
        port=port,
        reload=os.environ.get("AGENT_SALES_UI_RELOAD", "").lower() in ("1", "true", "yes"),
    )
