"""The ``api_refusals`` row (#828 item 1): pages and names the API refused. Pure: the shell passes the snapshot in.

The request guard (``backend/request_guard/``) refuses a request whose Host is not one
of the API's names and a socket from a page not on the CORS list. A browser shows a
refused socket only as close code 1006, so without this row the reason was only in the
engine log. The snapshot is ``request_guard.recent_refusals.snapshot()``.

Refused values are attacker-controlled text: the row shows them cut, unprintable
characters as "?", and reads them only to tell a local page from any other one.
They are named only in ``fix`` and kept in the evidence, never in ``detail`` or
``cause``: an issue filed from the desk prints those two (``issue_report/dump.py``,
``compose.auto_description``) and leaves out ``fix`` and the process group's
evidence, so a site the operator had open never lands in a public issue.
"""
from __future__ import annotations

import re
import time
from typing import Any

from constants import CORS_ALLOWED_ORIGINS_DEFAULT
from constants_diagnostics import DIAG_GROUP_PROCESS, DIAG_STATE_OK, DIAG_STATE_WARN
from diagnostics.rows import row
from request_guard.constants_request_guard import (
    ALLOWED_HOSTS_ENV,
    API_HOST_ENV,
    API_KEY_ENV,
    CORS_ORIGINS_ENV,
    REFUSAL_DIAG_RECENT_SEC,
    REFUSAL_DIAG_VALUE_SHOWN_MAX_CHARS,
    REFUSAL_DIAG_VALUES_SHOWN,
)

ROW_ID = "api_refusals"
ROW_TITLE = "Pages and names the API refused"

# A page served from this PC: probably the operator's own, on another port.
_LOCAL_PAGE = re.compile(r"http://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?", re.IGNORECASE)
# A browser extension has no tab to close; "null" comes from a sandboxed frame or a local HTML file.
_EXTENSION = re.compile(r"(?:chrome|moz|safari-web|ms-browser)-extension://\S*", re.IGNORECASE)
_OPAQUE_ORIGIN = "null"
_KIND_WORDS = {"websocket": "socket", "http": "request"}
# What the detail counts in place of the values: (one, several) per refused header.
_HEADER_NOUNS = {"Origin": ("page origin", "page origins"), "Host": ("Host name", "Host names"),
                 "": ("missing Host name", "missing Host names")}
_VITE_ORIGINS = " and ".join(CORS_ALLOWED_ORIGINS_DEFAULT)


def _shown(value: str) -> str:
    """A refused value as display text: never parsed, cut, unprintable characters as "?"."""
    if not value:
        return "(none sent)"
    text = "".join(ch if ch.isprintable() else "?" for ch in value)
    if len(text) > REFUSAL_DIAG_VALUE_SHOWN_MAX_CHARS:
        text = text[: REFUSAL_DIAG_VALUE_SHOWN_MAX_CHARS - 3] + "..."
    return text


def _ago(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return "under a minute ago"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h {minutes % 60} min ago"


def _times(count: int) -> str:
    return "1 time" if count == 1 else f"{count} times"


def _kind_word(entry: dict[str, Any]) -> str:
    return _KIND_WORDS.get(str(entry.get("kind")), str(entry.get("kind")))


def _describe(entry: dict[str, Any]) -> str:
    """One refused value, named: only for ``fix``."""
    count = int(entry.get("count") or 0)
    return f"{entry.get('header')} {_shown(str(entry.get('value') or ''))} ({_kind_word(entry)}, {_times(count)})"


def _counted(entries: list[dict[str, Any]]) -> str:
    """The refused values counted per header and kind, most recent first, never named: for ``detail``."""
    groups: dict[tuple[str, str], list[int]] = {}
    for entry in entries:
        header = str(entry.get("header"))
        noun = "" if header == "Host" and not entry.get("value") else header
        values_and_times = groups.setdefault((noun, _kind_word(entry)), [0, 0])
        values_and_times[0] += 1
        values_and_times[1] += int(entry.get("count") or 0)
    parts = []
    for (noun, kind), (values, count) in groups.items():
        one, several = _HEADER_NOUNS.get(noun, (f"{noun} value", f"{noun} values"))
        parts.append(f"{values} {one if values == 1 else several} ({kind}, {_times(count)})")
    return ", ".join(parts)


def _category(entry: dict[str, Any]) -> str:
    if entry.get("header") == "Host":
        return "host"
    value = str(entry.get("value") or "")
    if _LOCAL_PAGE.fullmatch(value):
        return "local_page"
    if _EXTENSION.fullmatch(value):
        return "extension"
    return "opaque" if value.lower() == _OPAQUE_ORIGIN else "web_page"


def _cause_and_fix(category: str, value: str) -> tuple[str, str]:
    """The cause never names the value (an issue report prints it); the fix does."""
    shown = _shown(value)
    if category == "local_page":
        return (
            "A page at an address on this PC -- probably your own page on another port -- "
            "tried to open Nova's live feeds. Sockets open only for the desk's own pages.",
            f"If the page at {shown} is yours, add its origin to {CORS_ORIGINS_ENV} in .env (list the Vite "
            f"origins {_VITE_ORIGINS} too, the list replaces them), then Reload backend. If you do "
            "not know what runs there, leave it refused.",
        )
    if category == "extension":
        return (
            "A browser extension on this PC tried to open Nova's live feeds "
            "and was refused before it reached any route.",
            f"If you don't recognise the extension {shown}, remove it from the browser.",
        )
    if category == "opaque":
        return (
            "A page with no origin of its own -- a frame sandboxed inside a website, or an HTML file "
            "opened from disk -- tried to open Nova's live feeds and was refused.",
            "If you did not just open such a page yourself, close the browser tabs you don't recognise.",
        )
    if category == "web_page":
        return (
            "A web page open in a browser on this PC tried to open Nova's live feeds "
            "and was refused before it reached any route.",
            f"If you don't recognise {shown}, close that tab.",
        )
    cause = ("The API answers only to its own names, so a web page that points its own name at "
             "this PC (DNS rebinding) is refused.")
    if not value:
        return f"Something reached the API without a Host name. {cause}", "Nothing to do: every request must name the API."
    return (
        f"Something reached the API by a name that is not one of its own. {cause}",
        f"If that is you reaching Nova as {shown} from another machine, add the name to "
        f"{ALLOWED_HOSTS_ENV} in .env (and set {API_HOST_ENV} and {API_KEY_ENV}), then Reload backend. "
        "Otherwise it was refused on purpose.",
    )


def refusal_rows(*, snapshot: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    t = time.time() if now is None else float(now)
    entries = sorted(snapshot.get("refusals") or [], key=lambda e: float(e.get("last_at") or 0), reverse=True)
    evidence = {**snapshot, "recent_window_sec": REFUSAL_DIAG_RECENT_SEC}
    base = dict(id=ROW_ID, group=DIAG_GROUP_PROCESS, title=ROW_TITLE, evidence=evidence)
    window_min = REFUSAL_DIAG_RECENT_SEC // 60
    if not entries:
        return [row(**base, state=DIAG_STATE_OK, detail="Nothing refused since the API started",
                    cause=("Every request named the API by one of its own names, and every socket came "
                           "from the desk's own pages or from a program, not a web page."),
                    fix="Nothing to do.")]
    recent = [e for e in entries if t - float(e.get("last_at") or 0) < REFUSAL_DIAG_RECENT_SEC]
    if not recent:
        latest = entries[0]
        return [row(**base, state=DIAG_STATE_OK,
                    detail=(f"Nothing refused in the last {window_min} min; last refused "
                            f"{_ago(t - float(latest.get('last_at') or 0))}: {_counted([latest])}"),
                    cause=(f"A refusal keeps this row yellow for {window_min} minutes. The evidence lists "
                           "every value refused since the API started."),
                    fix=f"Nothing to do. Last refused: {_describe(latest)}.")]
    detail = f"Refused, latest {_ago(t - float(recent[0].get('last_at') or 0))}: {_counted(recent)}"
    causes: list[str] = []
    fixes: list[str] = []
    others: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in recent:  # one cause and fix per kind of refusal, most recent first
        category = _category(entry)
        if category in seen:
            others.append(entry)
            continue
        seen.add(category)
        cause, fix = _cause_and_fix(category, str(entry.get("value") or ""))
        causes.append(cause)
        fixes.append(fix)
    if others:  # the values no fix above names
        shown = others[:REFUSAL_DIAG_VALUES_SHOWN]
        more = len(others) - len(shown)
        fixes.append("Also refused: " + ", ".join(_describe(e) for e in shown)
                     + (f", and {more} more" if more else "") + ".")
    causes.append("Counts are since the API started.")
    return [row(**base, state=DIAG_STATE_WARN, detail=detail, cause=" ".join(causes), fix=" ".join(fixes))]
