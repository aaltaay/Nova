"""Optional Pinecone re-ingest from the dream CLI."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PineconeResult:
    ran: bool
    dry_run: bool
    exit_code: int
    command: list[str]
    summary: str


def run_pinecone_ingest(
    repo_root: Path,
    *,
    write: bool,
    official_transcripts: bool = False,
    limit: int | None = 3,
) -> PineconeResult:
    """Invoke course_memory/ingest.py. Default dry-run unless write=True.

    ``limit`` caps files in dream-triggered runs to avoid multi-hour jobs;
    pass ``limit=None`` for a full ingest.
    """
    script = repo_root / "tools" / "course_memory" / "ingest.py"
    cmd = [sys.executable, str(script)]
    if official_transcripts:
        cmd.append("--official-transcripts")
    if not write:
        cmd.append("--dry-run")
    if limit is not None:
        cmd.extend(["--limit", str(limit)])

    if not script.is_file():
        return PineconeResult(
            ran=False,
            dry_run=not write,
            exit_code=2,
            command=cmd,
            summary="ingest.py missing",
        )

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return PineconeResult(
            ran=True,
            dry_run=not write,
            exit_code=124,
            command=cmd,
            summary="ingest timed out after 600s",
        )

    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-8:]
    summary = " | ".join(tail) if tail else f"exit={proc.returncode}"
    return PineconeResult(
        ran=True,
        dry_run=not write,
        exit_code=proc.returncode,
        command=cmd,
        summary=summary[:500],
    )
