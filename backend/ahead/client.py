"""The only HTTP caller of the private forecaster (ADR 061, contract ``ahead-forecaster/1``).

Two endpoints: ``GET /v1/health`` and ``POST /v1/forecast``, on loopback only (``config`` checks the address before
the token is ever sent), with the contract's deadlines, on this module's own two threads (``run_ask``) -- never the
FastAPI pool, never the reads' threads, never the IB loop. The session ignores proxy settings and never follows a
redirect, so the token goes to the checked address and nowhere else. Every failure is a ``ForecasterError`` in
Nova's own words; the answers are parsed strictly (``parse_health``, ``parse_forecast``): a missing or bad field is an
error naming the field, and nothing is defaulted.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, TypeVar

import requests

import http_pool
from ahead import config
from constants_ahead import (
    AHEAD_ASK_WORKERS,
    AHEAD_CONTRACT,
    AHEAD_ERROR,
    AHEAD_FORECAST_TIMEOUT_SEC,
    AHEAD_HEALTH_STATES,
    AHEAD_HEALTH_TIMEOUT_SEC,
    AHEAD_LEVEL_TOLERANCE,
    AHEAD_LEVELS,
    AHEAD_MAX_BODY_BYTES,
    AHEAD_MIN_PATHS,
    AHEAD_NOT_ENOUGH_BARS,
    AHEAD_NOT_SET_UP,
    AHEAD_OFFLINE,
    AHEAD_POOL,
    AHEAD_READ_CHUNK_BYTES,
    AHEAD_WARMING,
    AHEAD_WORDS_NO_CONNECT,
    AHEAD_WORDS_TOKEN_REFUSED,
    AHEAD_WORDS_UNREADABLE,
    AHEAD_WORDS_WARMING,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ForecasterError(RuntimeError):
    """A failed ask: the wire's ``ai.state`` and Nova's own words (never the exception's text)."""

    def __init__(self, state: str, message: str, *, need: int | None = None, transport: bool = False) -> None:
        super().__init__(message)
        self.state = state
        self.message = message
        self.need = need
        self.transport = transport      # no answer at all (timeout, refused connection): counts toward the breaker


# ---------------------------------------------------------------- strict parsing


def _missing(field: str) -> ForecasterError:
    return ForecasterError(AHEAD_ERROR, f"the forecaster's answer is missing {field}")


def _bad(field: str) -> ForecasterError:
    return ForecasterError(AHEAD_ERROR, f"the forecaster's answer has a bad {field}")


def _get(obj: Any, key: str, field: str) -> Any:
    if not isinstance(obj, dict) or key not in obj:
        raise _missing(field)
    return obj[key]


def _num(v: Any, field: str, *, positive: bool = False, nonneg: bool = False) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _bad(field)
    if (positive and v <= 0) or (nonneg and v < 0):
        raise _bad(field)
    return v


def _opt_num(v: Any, field: str) -> float | None:
    return None if v is None else _num(v, field)


def _count(v: Any, field: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise _bad(field)
    return v


def _text(v: Any, field: str) -> str:
    if not isinstance(v, str):
        raise _bad(field)
    return v


def _opt_text(v: Any, field: str) -> str | None:
    return None if v is None else _text(v, field)


def _flag(v: Any, field: str) -> bool:
    if not isinstance(v, bool):
        raise _bad(field)
    return v


def _row(v: Any, field: str, length: int, *, positive: bool = False, nonneg: bool = False,
         ascending: bool = False) -> list[float]:
    if not isinstance(v, list) or len(v) != length:
        raise _bad(field)
    row = [_num(x, field, positive=positive, nonneg=nonneg) for x in v]
    if ascending and any(b < a for a, b in zip(row, row[1:], strict=False)):
        raise _bad(field)
    return row


def _matrix(v: Any, field: str, rows: int, cols: int, **kw: bool) -> list[list[float]]:
    if not isinstance(v, list) or len(v) != rows:
        raise _bad(field)
    return [_row(r, field, cols, **kw) for r in v]


def _model(raw: Any) -> dict[str, str]:
    m = _get(raw, "model", "model")
    return {"name": _text(_get(m, "name", "model.name"), "model.name"),
            "version": _text(_get(m, "version", "model.version"), "model.version")}


def _contract(raw: Any) -> None:
    theirs = _get(raw, "contract", "contract")
    if theirs != AHEAD_CONTRACT:
        raise ForecasterError(AHEAD_ERROR, f"contract mismatch: the forecaster speaks {str(theirs)[:40]!r}")


def _score(raw: Any, field: str, *, named: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"name": _text(_get(raw, "name", f"{field}.name"), f"{field}.name")} if named else {}
    out["spearman"] = _num(_get(raw, "spearman", f"{field}.spearman"), f"{field}.spearman")
    out["miss_x"] = _num(_get(raw, "miss_x", f"{field}.miss_x"), f"{field}.miss_x")
    return out


def _exam(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    out: dict[str, Any] = {
        "passed": _flag(_get(raw, "passed", "exam.passed"), "exam.passed"),
        "as_of": _text(_get(raw, "as_of", "exam.as_of"), "exam.as_of"),
        "summary": _text(_get(raw, "summary", "exam.summary"), "exam.summary"),
        # A forecaster that does not say what its exam covered: null, and the desk prints "scope not stated".
        "scope": _opt_text(raw.get("scope"), "exam.scope"),
    }
    for part in ("volume", "range"):
        block = _get(raw, part, f"exam.{part}")
        out[part] = {"model": _score(_get(block, "model", f"exam.{part}.model"), f"exam.{part}.model"),
                     "baseline": _score(_get(block, "baseline", f"exam.{part}.baseline"), f"exam.{part}.baseline",
                                        named=True)}
    out["band80_coverage"] = _num(_get(raw, "band80_coverage", "exam.band80_coverage"), "exam.band80_coverage",
                                  nonneg=True)
    sample = _get(raw, "sample", "exam.sample")
    out["sample"] = {"days": _count(_get(sample, "days", "exam.sample.days"), "exam.sample.days"),
                     "moments": _count(_get(sample, "moments", "exam.sample.moments"), "exam.sample.moments")}
    return out


def _live(raw: Any) -> dict[str, Any]:
    return {
        "since": _opt_text(_get(raw, "since", "live.since"), "live.since"),
        "scored": _count(_get(raw, "scored", "live.scored"), "live.scored"),
        "volume_spearman": _opt_num(_get(raw, "volume_spearman", "live.volume_spearman"), "live.volume_spearman"),
        "range_spearman": _opt_num(_get(raw, "range_spearman", "live.range_spearman"), "live.range_spearman"),
        "band80_coverage": _opt_num(_get(raw, "band80_coverage", "live.band80_coverage"), "live.band80_coverage"),
    }


def parse_health(raw: Any) -> dict[str, Any]:
    """``/v1/health`` as ``{state, detail, model, exam, live}``; any bad field raises naming it."""
    _contract(raw)
    state = _get(raw, "state", "state")
    if state not in AHEAD_HEALTH_STATES:
        raise _bad("state")
    return {
        "state": state,
        "detail": _opt_text(raw.get("detail"), "detail"),
        "model": _model(raw),
        "exam": _exam(_get(raw, "exam", "exam")),
        "live": _live(_get(raw, "live", "live")),
    }


def _instant(iso: Any, field: str) -> float:
    try:
        when = datetime.fromisoformat(_text(iso, field))
    except ValueError:
        raise _bad(field) from None
    if when.tzinfo is None:
        raise _bad(field)
    return when.timestamp()


def _levels(raw: Any) -> list[float]:
    levels = _get(raw, "levels", "levels")
    if (not isinstance(levels, list) or len(levels) != len(AHEAD_LEVELS)
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or abs(x - want) > AHEAD_LEVEL_TOLERANCE
                   for x, want in zip(levels, AHEAD_LEVELS, strict=True))):
        raise _bad("levels")
    return list(AHEAD_LEVELS)


def parse_forecast(raw: Any, sym: str, as_of_iso: str, horizon: int) -> dict[str, Any]:
    """``/v1/forecast``'s answer, checked against the ask it answers; any bad field raises naming it.

    Each quantile row is non-decreasing (a row out of order is refused), prices are above zero and volumes not below it.
    """
    _contract(raw)
    if str(_get(raw, "symbol", "symbol")).upper() != sym.upper():
        raise _bad("symbol")
    if abs(_instant(_get(raw, "as_of", "as_of"), "as_of") - _instant(as_of_iso, "as_of")) > 1e-6:
        raise _bad("as_of")
    if _get(raw, "horizon_min", "horizon_min") != horizon:
        raise _bad("horizon_min")
    levels = _levels(raw)
    k = len(levels)
    paths = _get(raw, "paths", "paths")
    n = _get(paths, "n", "paths.n")
    if isinstance(n, bool) or not isinstance(n, int) or n < AHEAD_MIN_PATHS:
        raise _bad("paths.n")
    return {
        "model": _model(raw),
        "levels": levels,
        "close": _matrix(_get(raw, "close", "close"), "close", horizon, k, positive=True, ascending=True),
        "volume": _matrix(_get(raw, "volume", "volume"), "volume", horizon, k, nonneg=True, ascending=True),
        "paths": {"n": n,
                  "close": _matrix(_get(paths, "close", "paths.close"), "paths.close", n, horizon, positive=True),
                  "joined_by": _text(_get(paths, "joined_by", "paths.joined_by"), "paths.joined_by")},
        "volume_15": _row(_get(raw, "volume_15", "volume_15"), "volume_15", k, nonneg=True, ascending=True),
        "range_15": _row(_get(raw, "range_15", "range_15"), "range_15", k, nonneg=True, ascending=True),
        "exam_passed": _flag(_get(raw, "exam_passed", "exam_passed"), "exam_passed"),
        "compute_ms": _num(_get(raw, "compute_ms", "compute_ms"), "compute_ms", nonneg=True),
    }


# ---------------------------------------------------------------- asking

_pool_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=AHEAD_ASK_WORKERS, thread_name_prefix="ahead-ask")
        return _pool


async def run_ask(fn: Callable[..., T], *args: Any) -> T:
    """``fn(*args)`` on the forecaster's own threads."""
    return await asyncio.get_running_loop().run_in_executor(_executor(), functools.partial(fn, *args))


def reset_pool() -> None:
    """Tests: drop the forecaster's threads; the next ask makes new ones."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _session() -> requests.Session:
    s = http_pool.session(AHEAD_POOL)
    s.trust_env = False        # no proxy from the environment: the request goes to the checked loopback address
    return s


def _body(resp: Any, timeout: float, started: float) -> Any:
    """The answer's JSON, read in chunks up to the size cap and the deadline."""
    buf = bytearray()
    for chunk in resp.iter_content(AHEAD_READ_CHUNK_BYTES):
        buf.extend(chunk)
        if len(buf) > AHEAD_MAX_BODY_BYTES:
            raise ForecasterError(AHEAD_ERROR, AHEAD_WORDS_UNREADABLE)
        if time.monotonic() - started > timeout:
            raise ForecasterError(AHEAD_OFFLINE, f"no answer in {timeout:g} s", transport=True)
    try:
        return json.loads(bytes(buf))
    except ValueError:
        raise ForecasterError(AHEAD_ERROR, AHEAD_WORDS_UNREADABLE) from None


def _error_body(resp: Any, timeout: float, started: float) -> dict[str, Any]:
    """A refusal's JSON body (``{"error": ..., ...}``), or ``{}`` when it has none Nova can read (the refusal is then
    answered by its HTTP code alone)."""
    body: Any = None
    try:
        body = _body(resp, timeout, started)
    except ForecasterError as exc:
        logger.info("ahead: a refusal's body was unreadable (%s); its HTTP code answers", exc.message)
    return body if isinstance(body, dict) else {}


def _answer(resp: Any, timeout: float, started: float) -> Any:
    code = int(resp.status_code)
    if code == 200:
        return _body(resp, timeout, started)
    if code == 401:
        raise ForecasterError(AHEAD_ERROR, AHEAD_WORDS_TOKEN_REFUSED)
    if code == 409:
        body = _error_body(resp, timeout, started)
        need = body.get("need")
        if body.get("error") == "NOT_ENOUGH_BARS" and isinstance(need, int) and not isinstance(need, bool) and need > 0:
            raise ForecasterError(AHEAD_NOT_ENOUGH_BARS, f"the forecaster needs {need} one-minute candles", need=need)
    if code == 503 and _error_body(resp, timeout, started).get("error") == "WARMING":
        raise ForecasterError(AHEAD_WARMING, AHEAD_WORDS_WARMING)
    raise ForecasterError(AHEAD_ERROR, f"the forecaster answered HTTP {code}")


def _call(method: str, path: str, timeout: float, body: dict[str, Any] | None = None) -> Any:
    base, tok = config.base_url(), config.token()
    if base is None or tok is None:
        raise ForecasterError(AHEAD_NOT_SET_UP, config.setup_problem() or AHEAD_WORDS_NO_CONNECT)
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    started = time.monotonic()
    try:
        resp = _session().request(method, f"{base}{path}", headers=headers, json=body, timeout=timeout,
                                  stream=True, allow_redirects=False)
        try:
            return _answer(resp, timeout, started)
        finally:
            resp.close()
    except requests.Timeout:
        raise ForecasterError(AHEAD_OFFLINE, f"no answer in {timeout:g} s", transport=True) from None
    except requests.RequestException as exc:
        # The exception's type only: its text can carry the URL, and nothing about the request is logged.
        logger.info("ahead: %s %s failed (%s)", method, path, type(exc).__name__)
        raise ForecasterError(AHEAD_OFFLINE, AHEAD_WORDS_NO_CONNECT, transport=True) from None


def health() -> dict[str, Any]:
    """``GET /v1/health``, parsed. Blocking: call it through ``run_ask``."""
    return parse_health(_call("GET", "/v1/health", AHEAD_HEALTH_TIMEOUT_SEC))


def forecast(body: dict[str, Any]) -> dict[str, Any]:
    """``POST /v1/forecast`` with ``inputs.request_body``'s body, parsed. Blocking: call it through ``run_ask``."""
    raw = _call("POST", "/v1/forecast", AHEAD_FORECAST_TIMEOUT_SEC, body)
    return parse_forecast(raw, body["symbol"], body["as_of"], int(body["horizon_min"]))
