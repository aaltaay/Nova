"""A short setup's five-year test, as its card and the On lock read it (ADR 049 section 12). Read-only.

Owner: ``research/shorts/test_shorts.py`` writes ``<folder>/<setup>.json`` through a temporary file and a
rename; nothing in the backend writes one, and no agent does. The folder is ``NOVA_SHORT_TESTS_DIR``, else
``<NOVA_MARKET_DATA_DIR>/research/short_tests``. Invalidation: a read is kept ``SHORT_TESTS_CACHE_SEC``.
Schema: ``schema_version`` 1. A file that cannot be read, or of an unknown version, reads ``error`` -- never
passed: a result Nova cannot read never unlocks On.

``test(setup, params_hash)`` is the wire's ``test`` object (None on a long setup). ``lock(setup,
params_hash)`` says why On is locked, None once the test passed on the rules in play: the result's
``rules.rules_hash`` must equal the template in play's ``params_hash``, so an edited template tests again.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Any

from constants_bot import BOT_SHORT_SETUPS, SIDE_SHORT, setup_side
from constants_short_setups import (
    SHORT_TEST_COMMAND,
    SHORT_TEST_ERROR,
    SHORT_TEST_FAILED,
    SHORT_TEST_PASSED,
    SHORT_TEST_QUEUED,
    SHORT_TEST_RUNNING,
    SHORT_TEST_STATES,
    SHORT_TESTS_CACHE_SEC,
    SHORT_TESTS_DIR_ENV,
    SHORT_TESTS_SCHEMA_VERSION,
    SHORT_TESTS_STALE_SEC,
    SHORT_TESTS_SUBDIR,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any] | str | None]] = {}   # setup -> (read at, body | error | None)


def folder() -> Path:
    """Where the results live: ``NOVA_SHORT_TESTS_DIR``, else under the market data folder."""
    own = os.environ.get(SHORT_TESTS_DIR_ENV)
    if own:
        return Path(own)
    from sim.massive_files import root

    return root().joinpath(*SHORT_TESTS_SUBDIR)


def path_of(setup: str) -> Path:
    """The result file of one of the five short setups. Its name is the constant from ``BOT_SHORT_SETUPS``,
    never the caller's string, so no input reaches the path; anything else raises ``ValueError``."""
    known = next((name for name in BOT_SHORT_SETUPS if name == setup), None)
    if known is None:
        raise ValueError(f"not a short setup: {setup!r}")
    return folder() / f"{known}.json"


def _load(setup: str, now: float) -> dict[str, Any] | str | None:
    """The result file's body, or why it cannot be read (a string), or None when there is none yet."""
    with _lock:
        hit = _cache.get(setup)
        if hit is not None and now - hit[0] < SHORT_TESTS_CACHE_SEC:
            return hit[1]
    path = path_of(setup)
    try:
        body: dict[str, Any] | str | None = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        body = None
    except (OSError, ValueError) as exc:
        logger.warning("short tests: %s could not be read", path, exc_info=True)
        body = f"{path.name} could not be read: {exc}"
    if isinstance(body, dict) and body.get("schema_version") != SHORT_TESTS_SCHEMA_VERSION:
        body = f"{path.name} has schema version {body.get('schema_version')!r}; this build reads " \
               f"{SHORT_TESTS_SCHEMA_VERSION}"
    elif body is not None and not isinstance(body, (dict, str)):
        body = f"{path.name} is not a test result"
    with _lock:
        _cache[setup] = (now, body)
    return body


def _num(value: Any) -> float | None:
    """A finite number, else None: no wire frame carries a bare NaN or Infinity (Python's json reads both)."""
    try:
        out = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return out if out is not None and math.isfinite(out) else None


def _summary(body: dict[str, Any]) -> dict[str, Any] | None:
    main = body.get("main") if isinstance(body.get("main"), dict) else None
    criteria = body.get("criteria") if isinstance(body.get("criteria"), dict) else {}
    if main is None:
        return None
    costs = criteria.get("costs_2x") if isinstance(criteria.get("costs_2x"), dict) else {}
    perm = criteria.get("permutation") if isinstance(criteria.get("permutation"), dict) else {}
    trades = main.get("trades")
    return {"trades": int(trades) if isinstance(trades, (int, float)) else None, "pf": _num(main.get("pf")),
            "pf_2x": _num(costs.get("pf")), "exp_r": _num(main.get("exp_r")), "p": _num(perm.get("p"))}


def _words(state: str, body: dict[str, Any], matches: bool | None, now: float, command: str) -> str:
    if state == SHORT_TEST_RUNNING:
        progress = body.get("progress") if isinstance(body.get("progress"), dict) else {}
        done, total, unit = progress.get("done"), progress.get("total"), progress.get("unit") or "days"
        text = "five-year test running" + (f": {done} of {total} {unit}" if done is not None and total else "")
        updated = _num(body.get("updated_at"))
        if updated is not None and now - updated > SHORT_TESTS_STALE_SEC:
            text += f" -- no update for {int((now - updated) // 60)} min, so it may have stopped; run `{command}`"
        return text
    if state == SHORT_TEST_ERROR:
        return f"the five-year test stopped with an error ({body.get('error') or 'no reason given'}): run `{command}`"
    summary = _summary(body) or {}
    said = ", ".join(part for part in (
        f"{summary['trades']} trade{'' if summary['trades'] == 1 else 's'}" if summary.get("trades") is not None
        else None,
        f"PF {summary['pf']:.2f}" if summary.get("pf") is not None else None,
        f"{summary['exp_r']:+.2f}R a trade" if summary.get("exp_r") is not None else None,
    ) if part)
    verdict = "passed" if state == SHORT_TEST_PASSED else "failed"
    text = f"five-year test {verdict}" + (f" ({said})" if said else "")
    if state == SHORT_TEST_PASSED and matches is False:
        text += f" on other rules: the template in play has changed since, so it tests again (`{command}`)"
    return text


def test(setup: str, params_hash: str | None, *, now: float | None = None) -> dict[str, Any] | None:
    """``{state, text, rules_hash, matches, started_at, updated_at, finished_at, summary, file}`` for a short
    setup, None for a long one."""
    if setup_side(setup) != SIDE_SHORT:
        return None
    now = time.time() if now is None else now
    command = SHORT_TEST_COMMAND.format(setup=setup)
    body = _load(setup, now)
    file = str(path_of(setup))
    blank = {"rules_hash": None, "matches": None, "started_at": None, "updated_at": None, "finished_at": None,
             "summary": None, "file": file}
    if body is None:
        return {"state": SHORT_TEST_QUEUED, "text": f"five-year test queued: run `{command}` on the desk", **blank}
    if isinstance(body, str):
        return {"state": SHORT_TEST_ERROR, "text": body, **blank}
    state = str(body.get("state") or "")
    if state not in SHORT_TEST_STATES:
        return {"state": SHORT_TEST_ERROR, "text": f"{Path(file).name} says state {state!r}", **blank}
    rules = body.get("rules") if isinstance(body.get("rules"), dict) else {}
    rules_hash = rules.get("rules_hash")
    matches = None if rules_hash is None or params_hash is None else rules_hash == params_hash
    if state in (SHORT_TEST_PASSED, SHORT_TEST_FAILED) and body.get("passed") is not (state == SHORT_TEST_PASSED):
        return {"state": SHORT_TEST_ERROR, "text": f"{Path(file).name} says {state} but passed is "
                                                   f"{body.get('passed')!r}", **blank}
    return {"state": state, "text": _words(state, body, matches, now, command), "rules_hash": rules_hash,
            "matches": matches, "started_at": _num(body.get("started_at")), "updated_at": _num(body.get("updated_at")),
            "finished_at": _num(body.get("finished_at")),
            "summary": _summary(body) if state in (SHORT_TEST_PASSED, SHORT_TEST_FAILED) else None, "file": file}


def test_in_play(setup: str, *, now: float | None = None) -> dict[str, Any] | None:
    """``test`` against the setup's template in play (its ``params_hash``); a template store Nova cannot read
    reads ``error``, never passed."""
    if setup_side(setup) != SIDE_SHORT:
        return None
    try:
        from setup_templates.store import get_store

        params_hash = get_store().in_play(setup).fingerprint
    except Exception as exc:
        logger.warning("short tests: %s's template in play could not be read", setup, exc_info=True)
        return {"state": SHORT_TEST_ERROR, "text": f"the template in play could not be read ({exc})",
                "rules_hash": None, "matches": None, "started_at": None, "updated_at": None, "finished_at": None,
                "summary": None, "file": str(path_of(setup))}
    return test(setup, params_hash, now=now)


def lock(setup: str, params_hash: str | None, *, now: float | None = None) -> str | None:
    """Why a short setup cannot be On (ADR 049), else None: its test passed on the rules in play."""
    got = test(setup, params_hash, now=now)
    if got is None:
        return None
    if got["state"] == SHORT_TEST_PASSED and got["matches"]:
        return None
    return f"On waits on the {setup.replace('_', ' ')} five-year test: {got['text']}"


def reset_for_tests() -> None:
    with _lock:
        _cache.clear()
