"""Rotate a growing log file by size. Owner: scripts/Start-NovaApi.ps1.

Invalidation: size > max_bytes. Rotated names are dated; keep the newest N.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_KEEP = 5


def rotate_if_needed(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    keep: int = DEFAULT_KEEP,
    now: float | None = None,
) -> Path | None:
    """Rename ``path`` when it exceeds ``max_bytes``. Returns the rotated path."""
    target = Path(path)
    if not target.is_file():
        return None
    if target.stat().st_size < max_bytes:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now if now is not None else time.time()))
    rotated = target.with_name(f"{target.stem}-{stamp}{target.suffix}")
    index = 1
    while rotated.exists():
        rotated = target.with_name(f"{target.stem}-{stamp}-{index}{target.suffix}")
        index += 1
    target.rename(rotated)
    siblings = sorted(
        (
            p
            for p in target.parent.glob(f"{target.stem}-*{target.suffix}")
            if p.is_file() and p.name != target.name
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in siblings[keep:]:
        stale.unlink(missing_ok=True)
    return rotated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rotate a log file when it exceeds a size cap.")
    parser.add_argument("--path", required=True, help="Live log file path")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = parser.parse_args(argv)
    rotate_if_needed(Path(args.path), max_bytes=args.max_bytes, keep=args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
