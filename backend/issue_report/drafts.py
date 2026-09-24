"""A draft: the dump the form previews, kept until it is filed (or goes stale).

Opening the form builds one draft -- the context and the dump, scrubbed -- so what the operator
previews is exactly what is uploaded. Drafts live in memory for ``ISSUE_REPORT_DRAFT_TTL_SEC``
(at most ``ISSUE_REPORT_DRAFTS_KEEP``); ``build`` blocks (the diagnostics checklist probes the
Gateway ports, the engine log is read from disk), so the routes run it off the event loop.
A filed dump is also saved under the operator cache (``issue_dumps/``) -- the same scrubbed text.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from constants_issue_report import (
    ISSUE_REPORT_DRAFT_TTL_SEC,
    ISSUE_REPORT_DRAFTS_KEEP,
    ISSUE_REPORT_DUMP_DIR,
    ISSUE_REPORT_LOG_TAIL_BYTES,
)
from issue_report import compose, context
from issue_report.dump import Dump, parse_log, render_dump

logger = logging.getLogger(__name__)

_LOG_FILE = "blast.log"
_lock = threading.Lock()
_drafts: OrderedDict[str, Draft] = OrderedDict()


@dataclass(frozen=True)
class Draft:
    id: str
    created: float
    context: dict[str, Any] | None
    dump: Dump


def _read_log_tail(path: Path) -> str:
    with path.open("rb") as fh:
        size = fh.seek(0, 2)
        start = max(0, size - ISSUE_REPORT_LOG_TAIL_BYTES)
        fh.seek(start)
        data = fh.read()
    text = data.decode("utf-8", errors="replace")
    # Starting mid-file: drop the partial first line.
    return text.split("\n", 1)[1] if start and "\n" in text else text


def _checklist(ui_tag: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from diagnostics.gather import gather

        return gather(ui_tag=ui_tag), None
    except Exception as exc:
        logger.warning("issue_report: the diagnostics checklist failed", exc_info=True)
        return None, f"{type(exc).__name__}: {exc}"


def _log() -> tuple[str, str | None]:
    try:
        from paths import log_dir

        return _read_log_tail(Path(log_dir()) / _LOG_FILE), None
    except OSError as exc:
        logger.warning("issue_report: the engine log is unreadable", exc_info=True)
        return "", f"{type(exc).__name__}: {exc.strerror or exc}"


def _windows() -> tuple[list[dict[str, Any]], str | None]:
    try:
        from sensors import focus_store

        return list(focus_store.resolve().get("windows") or []), None
    except Exception as exc:
        # Stated in the dump as unreadable, never as "no window open".
        logger.warning("issue_report: the focus sensor is unreadable", exc_info=True)
        return [], f"{type(exc).__name__}: {exc}"


def build(*, now: float | None = None) -> Draft:
    """A new draft from the desk as it is now."""
    now = time.time() if now is None else now
    ctx = compose.clean_context(context.gather())
    diag, diag_error = _checklist((ctx or {}).get("ui"))
    log_text, log_error = _log()
    records, client_errors = parse_log(log_text)
    windows, windows_error = _windows()
    dump = render_dump(diag=diag, diag_error=diag_error, records=records, log_error=log_error,
                       client_errors=client_errors, windows=windows, windows_error=windows_error,
                       context_lines=compose.context_lines(ctx), now=now, scrubber=context.scrubber())
    draft = Draft(id=secrets.token_hex(8), created=now, context=ctx, dump=dump)
    with _lock:
        _prune(now)
        _drafts[draft.id] = draft
        while len(_drafts) > ISSUE_REPORT_DRAFTS_KEEP:
            _drafts.popitem(last=False)
    return draft


def _prune(now: float) -> None:
    for key in [k for k, d in _drafts.items() if now - d.created > ISSUE_REPORT_DRAFT_TTL_SEC]:
        del _drafts[key]


def get(draft_id: str | None, *, now: float | None = None) -> Draft | None:
    if not draft_id:
        return None
    now = time.time() if now is None else now
    with _lock:
        _prune(now)
        return _drafts.get(draft_id)


def save_copy(dump: Dump) -> bool:
    """Keep the filed dump on the desk too (the same scrubbed text); False when it could not be written."""
    try:
        from paths import cache_dir

        folder = Path(cache_dir()) / ISSUE_REPORT_DUMP_DIR
        folder.mkdir(parents=True, exist_ok=True)
        (folder / dump.file_name).write_text(dump.text, encoding="utf-8")
        return True
    except OSError:
        logger.warning("issue_report: the dump copy could not be saved", exc_info=True)
        return False


def reset_for_tests() -> None:
    with _lock:
        _drafts.clear()
