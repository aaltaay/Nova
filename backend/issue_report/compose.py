"""The issue the desk files -- pure: check the form, write what the operator left empty, compose.

Operator decision, 2026-09-24: "humans are not going to, given the time, give you a title or
description. If you allow them just to send a dump file, [it] will fill the title and
description." So for a bug the title and the description are optional: left empty, they are
written from the dump (``dump.Dump``) -- the failing checks, the newest engine errors, where the
operator was -- with no model and no tokens; the triage agent that reads the dump can retitle.
A feature needs a title or a line (a dump cannot say what the operator wants), and a report
with no words and no dump is refused.

The body is the words (typed or written), then a short "Filed from the Nova desk" block -- the
context the form showed, the checklist counts, the dump's link -- then a hidden record::

    <!-- nova-desk-issue {"schema_version": 1, "kind": "bug", "filed_at": ..., "dump": URL, ...} -->

The repository is public: typed text passes the same ``scrub.Scrubber`` as the dump, and the
context is rebuilt from checked fields only -- never free text.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from constants_bot import BOT_TZ
from constants_issue_report import (
    ISSUE_REPORT_AUTO_CLIENT_ERRORS,
    ISSUE_REPORT_AUTO_LOG_RECORDS,
    ISSUE_REPORT_AUTO_ROWS,
    ISSUE_REPORT_DETAILS_MAX,
    ISSUE_REPORT_KINDS,
    ISSUE_REPORT_NEW_URL,
    ISSUE_REPORT_SCHEMA_VERSION,
    ISSUE_REPORT_TITLE_MAX,
    ISSUE_REPORT_URL_BODY_MAX,
)
from constants_sensors import FOCUS_PAGES
from issue_report.dump import Dump
from issue_report.scrub import Scrubber

_TAG = re.compile(r"^v\d{1,6}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9./-]{0,11}$")
_TAB = re.compile(r"^[a-z0-9_-]{1,32}$")
_VENUES = {"live": "Live", "paper": "Paper", "sim": "Sim"}
_RECORD_COMMENT = re.compile(r"\n*<!-- nova-desk-issue .*? -->\n?", re.S)
_ET = ZoneInfo(BOT_TZ)


class IssueError(ValueError):
    """A form the desk cannot file: ``code`` for the answer, ``field`` names the input."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


@dataclass(frozen=True)
class DumpLink:
    """Where the dump went: its gist ``url``, or the ``error`` that kept it there."""

    file_name: str
    url: str | None
    error: str | None
    saved: bool


@dataclass(frozen=True)
class Composed:
    kind: str
    title: str
    body: str
    labels: list[str]
    auto_title: bool
    auto_description: bool
    removed: int


def _one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def check_kind(kind: Any) -> str:
    k = str(kind or "").strip().lower()
    if k not in ISSUE_REPORT_KINDS:
        raise IssueError("ISSUE_INVALID", f"kind must be one of {', '.join(ISSUE_REPORT_KINDS)}", "kind")
    return k


def check_title(title: Any) -> str:
    t = _one_line(title)
    if len(t) > ISSUE_REPORT_TITLE_MAX:
        raise IssueError("ISSUE_INVALID", f"the title is longer than {ISSUE_REPORT_TITLE_MAX} characters", "title")
    return t


def check_details(details: Any) -> str:
    d = str(details or "").replace("\r\n", "\n").strip()
    if len(d) > ISSUE_REPORT_DETAILS_MAX:
        raise IssueError("ISSUE_INVALID", f"the description is longer than {ISSUE_REPORT_DETAILS_MAX} characters",
                         "details")
    return d


def _pick(raw: dict[str, Any], key: str, pattern: re.Pattern[str], *, upper: bool = False) -> str | None:
    value = raw.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip().upper() if upper else value.strip()
    return value if pattern.match(value) else None


def clean_context(raw: Any) -> dict[str, str | None] | None:
    """The context the form showed, keeping only fields that pass their check (None: attach nothing)."""
    if not isinstance(raw, dict):
        return None
    venue = raw.get("venue") if raw.get("venue") in _VENUES else None
    page = raw.get("page") if raw.get("page") in FOCUS_PAGES else None
    out = {
        "nova": _pick(raw, "nova", _TAG),
        "commit": _pick(raw, "commit", _COMMIT),
        "ui": _pick(raw, "ui", _TAG),
        "venue": venue,
        "page": page,
        "tab": _pick(raw, "tab", _TAB) if page == "scanner" else None,
        "symbol": _pick(raw, "symbol", _SYMBOL, upper=True),
    }
    return out if any(out.values()) else None


def _where(context: dict[str, str | None] | None) -> str | None:
    if not context:
        return None
    page, tab, symbol = context.get("page"), context.get("tab"), context.get("symbol")
    if page:
        return str(page).capitalize() + (f" ({tab})" if tab else "") + (f" · {symbol}" if symbol else "")
    return symbol


def context_lines(context: dict[str, str | None] | None) -> list[str]:
    """What the form shows under "Desk details" and the body lists, one fact a line."""
    if not context:
        return []
    lines: list[str] = []
    nova, commit, ui = context.get("nova"), context.get("commit"), context.get("ui")
    if nova:
        lines.append(f"Nova {nova}" + (f" ({commit})" if commit else ""))
    elif commit:
        lines.append(f"Nova commit {commit}")
    if ui and ui != nova:
        lines.append(f"Desk window {ui}")
    if context.get("venue"):
        lines.append(f"Venue: {_VENUES[str(context['venue'])]}")
    where = _where(context)
    if where:
        lines.append(f"Page: {where}" if context.get("page") else f"Symbol: {where}")
    return lines


def _headline(dump: Dump | None) -> str:
    if dump is not None:
        fails = [w for w in dump.wrong if w["state"] == "fail"]
        if fails:
            return f"{fails[0]['title']} — {fails[0]['detail']}"
        if dump.errors:
            return f"{dump.errors[0].logger}: {dump.errors[0].message}"
        if dump.client_errors:
            return f"desk error: {dump.client_errors[0].message}"
    return "no failing check"


def auto_title(kind: str, details: str, dump: Dump | None, context: dict[str, str | None] | None,
               filed_at: float) -> str:
    """A title for a report the operator did not title."""
    if kind == "feature" or details:
        first = _one_line(details.split("\n", 1)[0])
        return _cut(first, ISSUE_REPORT_TITLE_MAX)
    when = datetime.fromtimestamp(filed_at, _ET).strftime("%H:%M ET")
    where = _where(context)
    suffix = f" ({where}, {when})" if where else f" ({when})"
    head = _cut(_one_line(_headline(dump)), ISSUE_REPORT_TITLE_MAX - len("Desk report: ") - len(suffix))
    return f"Desk report: {head}{suffix}"


def auto_description(dump: Dump, context: dict[str, str | None] | None) -> str:
    """What the dump says, briefly, for a report the operator did not describe."""
    parts = ["_No description was written; Nova summarized the dump._"]
    if dump.wrong:
        shown = dump.wrong[:ISSUE_REPORT_AUTO_ROWS]
        more = len(dump.wrong) - len(shown)
        parts.append("**What looks wrong**\n" + "\n".join(
            f"- `{w['state'].upper() if w['state'] == 'fail' else w['state']}` {w['title']}: {w['detail']}" for w in shown)
            + (f"\n- … and {more} more in the dump" if more > 0 else ""))
    if dump.errors:
        label = "Latest engine errors" if dump.errors[0].level in ("ERROR", "CRITICAL") else "Latest engine warnings"
        parts.append(f"**{label}**\n" + "\n".join(
            f"- {r.time} {r.logger}: {_cut(r.message, 240)}" + (f" (x{r.count})" if r.count > 1 else "")
            for r in dump.errors[:ISSUE_REPORT_AUTO_LOG_RECORDS]))
    if dump.client_errors:
        parts.append("**Latest desk window errors**\n" + "\n".join(
            f"- {c.time} {c.source}: {_cut(c.message, 240)}" for c in dump.client_errors[:ISSUE_REPORT_AUTO_CLIENT_ERRORS]))
    if len(parts) == 1:
        where = _where(context)
        parts.append("No check is failing and nothing was logged as an error"
                     + (f"; the operator filed this from {where}" if where else "")
                     + ". The dump holds the desk's state at that moment.")
    return "\n\n".join(parts)


def _record(kind: str, filed_at: float, context: dict[str, str | None] | None, dump: DumpLink | None,
            auto: tuple[bool, bool]) -> str:
    record = {"schema_version": ISSUE_REPORT_SCHEMA_VERSION, "kind": kind, "filed_at": int(filed_at),
              "context": context, "dump": (dump.url if dump else None),
              "dump_file": (dump.file_name if dump else None), "auto_title": auto[0], "auto_description": auto[1]}
    text = json.dumps(record, separators=(",", ":"), sort_keys=True)
    # Never let the record close its own comment.
    return text.replace("<", "\\u003c").replace(">", "\\u003e")


def _dump_line(link: DumpLink) -> str:
    if link.url:
        return f"Diagnostics dump: [{link.file_name}]({link.url})"
    where = f"; saved on the desk as `{link.file_name}`" if link.saved else ""
    return f"Diagnostics dump: not uploaded ({link.error or 'unknown error'}){where}"


def compose_issue(*, kind: Any, title: Any, details: Any, context: Any, filed_at: float, scrubber: Scrubber,
                  dump: Dump | None = None, dump_link: DumpLink | None = None) -> Composed:
    k = check_kind(kind)
    typed_title, typed_details = check_title(title), check_details(details)
    if k == "feature" and not (typed_title or typed_details):
        raise IssueError("ISSUE_INVALID", "say what you want Nova to do -- a title or one line is enough", "title")
    if not (typed_title or typed_details or dump):
        raise IssueError("ISSUE_INVALID", "type a line or attach the dump -- an empty report says nothing", "details")
    ctx = clean_context(context)
    t = scrubber.text(typed_title) if typed_title else auto_title(k, scrubber.text(typed_details), dump, ctx, filed_at)
    if typed_details:
        d = scrubber.text(typed_details)
    elif dump is not None:
        d = auto_description(dump, ctx)
    else:
        d = "_No description was written._"
    label, github_label = ISSUE_REPORT_KINDS[k]
    when = datetime.fromtimestamp(filed_at, _ET).strftime("%Y-%m-%d %H:%M ET")
    footer = [f"**Filed from the Nova desk** — {label}, {when}"]
    footer += [f"- {line}" for line in context_lines(ctx)]
    if dump is not None:
        footer.append(f"- Checklist: {dump.summary.get('fail', 0)} fail, {dump.summary.get('warn', 0)} warn "
                      f"of {dump.summary.get('rows', 0)} rows")
    if dump_link is not None:
        footer.append(f"- {_dump_line(dump_link)}")
    auto = (not typed_title, not typed_details)
    body = (f"{d}\n\n---\n" + "\n".join(footer)
            + f"\n\n<!-- nova-desk-issue {_record(k, filed_at, ctx, dump_link, auto)} -->\n")
    return Composed(kind=k, title=t, body=body, labels=[github_label], auto_title=auto[0],
                    auto_description=auto[1], removed=scrubber.count)


def new_issue_url(composed: Composed) -> str:
    """GitHub's new-issue page, prefilled -- for the operator to submit when the desk cannot."""
    body = composed.body
    if len(body) > ISSUE_REPORT_URL_BODY_MAX:
        # Cut the visible text only: half a hidden record would hide everything after it.
        visible = _RECORD_COMMENT.sub("", body).rstrip()
        body = visible[:ISSUE_REPORT_URL_BODY_MAX].rstrip() + "\n\n(cut to fit the link)"
    query = urlencode({"title": composed.title, "body": body, "labels": ",".join(composed.labels)},
                      quote_via=quote)
    return f"{ISSUE_REPORT_NEW_URL}?{query}"
