"""The feed's day, its trades across days and its evidence images, read over HTTP and checked field by field.

``fetch_day`` answers the day as Nova reads it (``parse_day``), ``fetch_trades`` a span of days
(``parse_range``) and ``fetch_reads`` a day's read log (``parse_reads``), with every time as epoch seconds, or raises
``FeedError`` with the state the page shows: ``unreachable`` (no answer, an HTTP error) or ``bad_answer`` (a field
Nova reads is missing or of another type, named in the message). Nothing is filled in; fields Nova does not read
are ignored. The feed's format: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from typing import Any

import requests

import http_pool
from followed_traders.constants_followed import (
    FOLLOWED_EVIDENCE_MAX_BYTES,
    FOLLOWED_FEED_TIMEOUT_SEC,
    FOLLOWED_READS_MAX_BYTES,
    FOLLOWED_USER_AGENT,
)

logger = logging.getLogger(__name__)
POOL = "followed_traders"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EVIDENCE_RE = re.compile(r"^frames/([0-9a-f]{32})\.jpg$")
NAME_RE = re.compile(r"^[A-Z0-9]{1,16}$")  # a trader's name as a file name in the feed's images
SLOT_RE = re.compile(r"^live/([A-Z0-9]{1,16})\.jpg$")
FACE_RE = re.compile(r"^faces/([A-Z0-9]{1,16})\.jpg$")
# A YouTube video id: the only shape the desk builds a player or a link from.
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CLOCK_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
SIDES = ("long", "short")
STATUSES = ("open", "closed", "unknown")


class FeedError(RuntimeError):
    """The feed did not answer (``unreachable``), answered something Nova cannot read (``bad_answer``), or has no
    such file (``missing``: its 404, only where the caller allows one)."""

    def __init__(self, state: str, message: str) -> None:
        super().__init__(message)
        self.state = state
        self.message = message  # Nova's own words, the only text a route sends (never str(exc))


def fetch_day(base: str, date: str | None, *, timeout: float = FOLLOWED_FEED_TIMEOUT_SEC) -> dict[str, Any]:
    resp = _get(f"{base}/api/day", params={"date": date} if date else None, timeout=timeout,
                accept="application/json")
    try:
        raw = resp.json()
    except ValueError as exc:
        raise FeedError("bad_answer", "the answer is not JSON") from exc
    return parse_day(raw)


def fetch_trades(base: str, start: str | None, end: str, *, timeout: float = FOLLOWED_FEED_TIMEOUT_SEC) -> dict[str, Any]:
    """Every trade from ``start`` (None: the feed's first day) to ``end``, each with its ``date``."""
    params = {"to": end} if start is None else {"from": start, "to": end}
    resp = _get(f"{base}/api/trades", params=params, timeout=timeout, accept="application/json")
    try:
        raw = resp.json()
    except ValueError as exc:
        raise FeedError("bad_answer", "the answer is not JSON") from exc
    return parse_range(raw)


def fetch_evidence(base: str, date: str, name: str, *, timeout: float = FOLLOWED_FEED_TIMEOUT_SEC) -> bytes:
    """The evidence JPEG ``frames/<name>.jpg`` of ``date``. The caller has checked both against the schema."""
    return _fetch_bytes(f"{base}/files/{date}/frames/{name}.jpg", timeout=timeout, accept="image/jpeg",
                        cap=FOLLOWED_EVIDENCE_MAX_BYTES, what="the image")


def fetch_live(base: str, name: str, *, timeout: float = FOLLOWED_FEED_TIMEOUT_SEC) -> bytes:
    """A trader's slot as the feed last saw it, ``live/<name>.jpg``; ``missing`` when the feed has none."""
    return _fetch_bytes(f"{base}/files/live/{name}.jpg", timeout=timeout, accept="image/jpeg",
                        cap=FOLLOWED_EVIDENCE_MAX_BYTES, what="the image", missing_ok=True)


def fetch_face(base: str, date: str, name: str, *, timeout: float = FOLLOWED_FEED_TIMEOUT_SEC) -> bytes:
    """A trader's photo that day, ``<date>/faces/<name>.jpg``; ``missing`` when the feed has none."""
    return _fetch_bytes(f"{base}/files/{date}/faces/{name}.jpg", timeout=timeout, accept="image/jpeg",
                        cap=FOLLOWED_EVIDENCE_MAX_BYTES, what="the image", missing_ok=True)


def fetch_reads(base: str, date: str, *, timeout: float = FOLLOWED_FEED_TIMEOUT_SEC) -> list[dict[str, Any]]:
    """The day's read log (``parse_reads``); ``missing`` when the feed keeps none for that day."""
    body = _fetch_bytes(f"{base}/files/{date}/reads.jsonl", timeout=timeout, accept="application/json",
                        cap=FOLLOWED_READS_MAX_BYTES, what="the read log", missing_ok=True)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FeedError("bad_answer", "the read log is not UTF-8") from exc
    return parse_reads(text)


def _fetch_bytes(url: str, *, timeout: float, accept: str, cap: int, what: str, missing_ok: bool = False) -> bytes:
    resp = _get(url, params=None, timeout=timeout, accept=accept, stream=True, missing_ok=missing_ok)
    body = bytearray()
    for chunk in resp.iter_content(64 * 1024):
        body += chunk
        if len(body) > cap:
            resp.close()
            raise FeedError("bad_answer", f"{what} is over {cap} bytes")
    return bytes(body)


def _get(url: str, *, params: dict | None, timeout: float, accept: str, stream: bool = False,
         missing_ok: bool = False) -> requests.Response:
    try:
        resp = http_pool.get(POOL, url, params=params, timeout=timeout, stream=stream,
                             headers={"User-Agent": FOLLOWED_USER_AGENT, "Accept": accept})
    except requests.Timeout as exc:
        raise FeedError("unreachable", f"timed out after {timeout:.0f} s") from exc
    except requests.RequestException as exc:
        logger.info("followed traders: the feed at %s did not answer: %s", url, type(exc).__name__)
        raise FeedError("unreachable", "could not connect") from exc
    if resp.status_code == 404 and missing_ok:
        resp.close()
        raise FeedError("missing", "HTTP 404")
    if resp.status_code != 200:
        resp.close()
        raise FeedError("unreachable", f"HTTP {resp.status_code}")
    return resp


# -- the day, as Nova reads it -----------------------------------------------------------------------


def parse_day(raw: Any) -> dict[str, Any]:
    """``{date, today, dates, status, trades}`` with times as epoch seconds; raises ``FeedError('bad_answer')``."""
    day = _obj(raw, "the answer")
    status = day.get("status")
    trades = _list(day, "trades", "the answer")
    return {
        "date": _date(day, "date"),
        "today": _date(day, "today"),
        "dates": [_date_value(d, f"dates[{i}]") for i, d in enumerate(_list(day, "dates", "the answer"))],
        "status": None if status is None else _status(_obj(status, "status")),
        "trades": [_trade(_obj(t, f"trades[{i}]"), f"trades[{i}]") for i, t in enumerate(trades)],
        "faces": _image_names(day, "faces", "the answer", FACE_RE),
    }


def parse_range(raw: Any) -> dict[str, Any]:
    """``{from, to, dates, trades}``: the feed's trades across days, each with its ``date``."""
    got = _obj(raw, "the answer")
    trades = _list(got, "trades", "the answer")
    out = []
    for i, t in enumerate(trades):
        t = _obj(t, f"trades[{i}]")
        out.append(_trade(t, f"trades[{i}]") | {"date": _date_value(t.get("date"), f"trades[{i}].date")})
    start = got.get("from")
    return {"from": start if isinstance(start, str) else None, "to": _date(got, "to"),
            "dates": [_date_value(d, f"dates[{i}]") for i, d in enumerate(_list(got, "dates", "the answer"))],
            "trades": out}


def _status(st: dict) -> dict[str, Any]:
    problem = {"problem": _str(st, "problem", "status", optional=True),
               "problem_at": _ts(st, "problem_at", "status", optional=True)}
    if "video" not in st and problem["problem"] is not None:
        # The feed stalled before it ever read a frame: its status holds only why.
        return {"title": None, "video_id": None, "live": False, "clock": None, "updated_at": None,
                "bar_visible": False, "traders": [], "positions": None, "slots": set(), **problem}
    video = _obj(st.get("video"), "status.video")
    traders = _list(st, "traders", "status")
    return {
        "title": _str(video, "title", "status.video", optional=True),
        "video_id": _video_id(video),
        "live": _bool(st, "live", "status"),
        "clock": _clock(st),
        "updated_at": _ts(st, "updated_at", "status", optional=True),
        "bar_visible": _bool(st, "bar_visible", "status"),
        "traders": [_str_value(n, f"status.traders[{i}]") for i, n in enumerate(traders)],
        "positions": _bar(st),
        "slots": _image_names(st, "slots", "status", SLOT_RE),
        **problem,
    }


def _time_of_day(clock: str) -> bool:
    h, m, s = (int(p) for p in clock.split(":"))
    return h < 24 and m < 60 and s < 60


def _clock(st: dict) -> str | None:
    """``status.clock``, or None when it is no time of day (a misread screen: ``09:34:97``)."""
    clock = _str(st, "clock", "status", optional=True)
    return clock if clock is not None and CLOCK_RE.match(clock) and _time_of_day(clock) else None


def _video_id(video: dict) -> str | None:
    """``status.video.id``, the stream the feed reads, when it is a YouTube video id; anything else is none, never a
    bad answer (the id is optional), so the desk never builds a player or a link from it."""
    vid = video.get("id")
    return vid if isinstance(vid, str) and VIDEO_ID_RE.fullmatch(vid) else None


def _bar(st: dict) -> list[dict[str, Any]] | None:
    """``status.positions``: each trader's bar as the feed last confirmed it, in the feed's order; None without."""
    raw = st.get("positions")
    if raw is None:
        return None
    return [{"trader": trader, "positions": _positions(held, f"status.positions.{trader}")}
            for trader, held in _obj(raw, "status.positions").items()]


def _positions(raw: Any, where: str) -> list[dict[str, Any]]:
    """``{"<side>:<symbol>": price}`` as ``[{side, symbol, price}]``, in the feed's order."""
    out = []
    for key, price in _obj(raw, where).items():
        side, _, symbol = key.partition(":")
        if side not in SIDES or not symbol:
            raise _bad(where, f"keyed {key!r}, not side:symbol")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price):
            raise _bad(f"{where}.{key}", "not a number")
        out.append({"side": side, "symbol": symbol, "price": float(price)})
    return out


def _image_names(obj: dict, key: str, where: str, path_re: re.Pattern) -> set[str]:
    """An optional ``{<trader>: "<path>"}`` map: the traders whose image is at the one path Nova may ask for."""
    raw = obj.get(key)
    if raw is None:
        return set()
    out = set()
    for trader, path in _obj(raw, key if where == "the answer" else f"{where}.{key}").items():
        m = path_re.match(_str_value(path, f"{key}.{trader}"))
        if m and m.group(1) == trader:
            out.add(trader)
    return out


# -- the read log ------------------------------------------------------------------------------------


def parse_reads(text: str) -> list[dict[str, Any]]:
    """``reads.jsonl`` as ``[{clock, traders: {name: {positions: [...], unparsed: [...]}}}]``, in the file's order;
    a line whose ``clock`` is null is skipped. The line after one or more skipped lines carries
    ``unread_before: True``: the bar was read somewhere between it and the line before, at times the log cannot say."""
    out = []
    skipped = False
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        where = f"reads.jsonl line {n}"
        try:
            raw = json.loads(line)
        except ValueError as exc:
            raise FeedError("bad_answer", f"{where} is not JSON") from exc
        rec = _obj(raw, where)
        clock = _str(rec, "clock", where, optional=True)
        if clock is None:
            skipped = True
            continue  # a frame the feed could not read at all: no time to place it at
        if not CLOCK_RE.match(clock):
            raise _bad(f"{where}.clock", f"{clock!r}, not HH:MM:SS")
        if not _time_of_day(clock):
            skipped = True
            continue  # a screen clock read impossibly (09:34:97): no time to place the line at
        traders = {}
        for name, read in _obj(rec.get("traders"), f"{where}.traders").items():
            read = _obj(read, f"{where}.traders.{name}")
            unparsed = [_str_value(u, f"{where}.traders.{name}.unparsed[{i}]")
                        for i, u in enumerate(_list(read, "unparsed", f"{where}.traders.{name}"))]
            traders[name] = {"positions": _positions(read.get("positions"), f"{where}.traders.{name}.positions"),
                             "unparsed": unparsed}
        out.append({"clock": clock, "traders": traders, **({"unread_before": True} if skipped else {})})
        skipped = False
    return out


def _trade(t: dict, where: str) -> dict[str, Any]:
    side = _str(t, "side", where)
    status = _str(t, "status", where)
    if side not in SIDES:
        raise FeedError("bad_answer", f"{where}.side is {side!r}, not long or short")
    if status not in STATUSES:
        raise FeedError("bad_answer", f"{where}.status is {status!r}, not open, closed or unknown")
    adds = []
    for i, a in enumerate(_list(t, "adds", where)):
        a = _obj(a, f"{where}.adds[{i}]")
        adds.append({"ts": _ts(a, "ts", f"{where}.adds[{i}]"), "price": _num(a, "price", f"{where}.adds[{i}]"),
                     "prev_price": _num(a, "prev_price", f"{where}.adds[{i}]", optional=True)})
    return {
        "trader": _str(t, "trader", where),
        "side": side,
        "symbol": _str(t, "symbol", where),
        "entry_price": _num(t, "entry_price", where),
        "price": _num(t, "price", where),
        "entry_ts": _ts(t, "entry_ts", where),
        "entry_since_ts": _ts(t, "entry_since_ts", where, optional=True),
        "entry_known": _bool(t, "entry_known", where),
        "adds": adds,
        "exit_ts": _ts(t, "exit_ts", where, optional=True),
        "exit_since_ts": _ts(t, "exit_since_ts", where, optional=True),
        "status": status,
        "entry_evidence": _str(t, "entry_evidence", where, optional=True),
        "exit_evidence": _str(t, "exit_evidence", where, optional=True),
        "read_as": _read_as(t, where),
    }


def _read_as(t: dict, where: str) -> str | None:
    """The ticker the feed first read for a trade it later corrected (``read_as.symbol``); None when it never did."""
    raw = t.get("read_as")
    if raw is None:
        return None
    return _str(_obj(raw, f"{where}.read_as"), "symbol", f"{where}.read_as")


def evidence_name(path: str | None) -> str | None:
    """The 32-hex name of a ``frames/<name>.jpg`` evidence path; None for anything else."""
    m = EVIDENCE_RE.match(path or "")
    return m.group(1) if m else None


# -- field readers: each raises FeedError('bad_answer') naming the field ------------------------------


def _bad(where: str, what: str) -> FeedError:
    return FeedError("bad_answer", f"{where} is {what}")


def _obj(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise _bad(where, "missing or not an object")
    return value


def _list(obj: dict, key: str, where: str) -> list:
    value = obj.get(key)
    if not isinstance(value, list):
        raise _bad(f"{where}.{key}" if where != "the answer" else key, "missing or not a list")
    return value


def _str(obj: dict, key: str, where: str, *, optional: bool = False) -> str | None:
    value = obj.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise _bad(f"{where}.{key}", "missing or not a string")
    return value


def _str_value(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise _bad(where, "not a string")
    return value


def _bool(obj: dict, key: str, where: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise _bad(f"{where}.{key}", "missing or not true/false")
    return value


def _num(obj: dict, key: str, where: str, *, optional: bool = False) -> float | None:
    value = obj.get(key)
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _bad(f"{where}.{key}", "missing or not a number")
    return float(value)


def _ts(obj: dict, key: str, where: str, *, optional: bool = False) -> float | None:
    """An ISO 8601 time with its offset, as epoch seconds; a time without an offset is not read."""
    value = _str(obj, key, where, optional=optional)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _bad(f"{where}.{key}", f"{value!r}, not an ISO 8601 time") from exc
    if parsed.tzinfo is None:
        raise _bad(f"{where}.{key}", f"{value!r}, a time without its offset")
    return parsed.timestamp()


def _date(obj: dict, key: str) -> str:
    return _date_value(obj.get(key), key)


def _date_value(value: Any, where: str) -> str:
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise _bad(where, "missing or not YYYY-MM-DD")
    return value
