"""Fold stall stack samples into counted stacks (ADR 026). Pure.

A sample is a tuple of ``(filename, lineno, function)`` frames, outermost
first. The report names each frame ``path:line function`` with the path made
relative to the repository when it is inside it.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from types import FrameType

Frame = tuple[str, int, str]

REPO_ROOT = str(Path(__file__).resolve().parents[2])
# The recorder's own frames (a GC callback caught mid-collection) never name a stall.
_SELF = os.path.normcase(str(Path(__file__).resolve().parent))


def capture(frame: FrameType | None, max_frames: int) -> tuple[Frame, ...]:
    """The innermost ``max_frames`` frames of a thread's stack, outermost first."""
    out: list[Frame] = []
    while frame is not None and len(out) < max_frames:
        code = frame.f_code
        out.append((code.co_filename, frame.f_lineno, code.co_name))
        frame = frame.f_back
    out.reverse()
    return tuple(out)


def frame_label(frame: Frame, repo_root: str = REPO_ROOT) -> str:
    filename, lineno, function = frame
    path = filename
    try:
        if os.path.normcase(os.path.abspath(filename)).startswith(os.path.normcase(repo_root)):
            path = os.path.relpath(filename, repo_root)
    except ValueError:
        # Different drive on Windows: keep the absolute path.
        path = filename
    return f"{path.replace(os.sep, '/')}:{lineno} {function}"


def in_repo(frame: Frame, repo_root: str = REPO_ROOT) -> bool:
    filename = os.path.normcase(os.path.abspath(frame[0]))
    return (filename.startswith(os.path.normcase(repo_root)) and "site-packages" not in filename
            and not filename.startswith(_SELF))


def fold(
    samples: list[tuple[Frame, ...]],
    top: int,
    repo_root: str = REPO_ROOT,
) -> tuple[list[dict], str | None]:
    """Counted stacks (most-sampled first, at most ``top``) and the top frame.

    The top frame is the innermost frame inside the repository that appears
    in the most samples -- the Nova line that was running, not the library
    call beneath it, nor the recorder's own GC hook when a collection was
    caught in progress (the stack still shows it). ``None`` when no sample
    touched the repository.
    """
    stacks = Counter(samples)
    innermost: Counter[Frame] = Counter()
    for stack, count in stacks.items():
        for frame in reversed(stack):
            if in_repo(frame, repo_root):
                innermost[frame] += count
                break
    top_frame = frame_label(innermost.most_common(1)[0][0], repo_root) if innermost else None
    folded = [
        {"count": count, "frames": [frame_label(f, repo_root) for f in stack]}
        for stack, count in stacks.most_common(top)
    ]
    return folded, top_frame
