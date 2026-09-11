"""IB-loop hot-lane purity: no sync I/O in callback modules (ADR 010)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

FindingFactory = Callable[..., object]

IB_LOOP_PURITY_RELS = (
    "backend/ibkr/ticks.py",
    "backend/ibkr/tape_stream.py",
    "backend/ibkr/scanner_l1.py",
    "backend/ibkr/scanner_stream.py",
    "backend/ibkr/cancel_verify.py",
    "backend/ibkr/historical_service.py",
    "backend/archive/capture.py",
    "backend/execution/telemetry.py",
    "backend/execution/telemetry_handlers.py",
    "backend/execution/telemetry_persist.py",
)
IB_LOOP_SYNC_IO_NEEDLES: tuple[tuple[str, str], ...] = (
    ("sqlite3.", "sync sqlite3 on IB-callback module -- enqueue instead (ADR 010)"),
    ("time.sleep(", "time.sleep on IB-callback module -- blocks the IB loop"),
    ("requests.", "sync requests on IB-callback module"),
)


def check_ib_loop_purity(
    files: list[Path],
    rel: Callable[[Path], str],
    finding: FindingFactory,
) -> list:
    wanted = {p.replace("\\", "/") for p in IB_LOOP_PURITY_RELS}
    findings: list = []
    for path in files:
        path_rel = rel(path).replace("\\", "/")
        if path_rel not in wanted:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for needle, detail in IB_LOOP_SYNC_IO_NEEDLES:
            start = 0
            while True:
                idx = text.find(needle, start)
                if idx < 0:
                    break
                line_no = text.count("\n", 0, idx) + 1
                line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
                if line_text.lstrip().startswith("#"):
                    start = idx + len(needle)
                    continue
                findings.append(
                    finding(
                        kind="ib_loop_sync_io",
                        path=path_rel,
                        detail=f"{detail}: {needle}",
                        line=line_no,
                    )
                )
                start = idx + len(needle)
    return findings
