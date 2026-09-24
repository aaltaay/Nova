"""The desk dump attached to an issue -- pure: parse the engine log, render the text.

The dump is what an agent reads to understand a report the operator filed without words, so it
carries the debugging facts and nothing about the PC (every line passes ``scrub.Scrubber``):

    Nova desk dump -- 2026-09-24 10:54 ET
    ## Summary          counts, where the operator was, what is failing
    ## Desk checklist   every diagnostics row: state, detail, cause, evidence (not for the rows
                        about this PC -- process and integrations -- whose evidence is paths
                        and key names)
    ## Engine log       the latest warnings and errors, repeats folded (x N)
    ## Desk windows     errors the desk windows reported; each window's page and symbol
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_bot import BOT_TZ
from constants_issue_report import (
    ISSUE_REPORT_CLIENT_ERRORS,
    ISSUE_REPORT_DUMP_MAX_CHARS,
    ISSUE_REPORT_DUMP_SCHEMA_VERSION,
    ISSUE_REPORT_LOG_LINE_MAX,
    ISSUE_REPORT_LOG_RECORDS,
    ISSUE_REPORT_PRIVATE_EVIDENCE_GROUPS,
)
from issue_report.scrub import Scrubber

_ET = ZoneInfo(BOT_TZ)
_RECORD_START = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}),\d{3} ([A-Z]+) (\S+) ?(.*)$")
_WANTED = {"WARNING", "ERROR", "CRITICAL"}
_CLIENT_LOGGER = "nova.client_errors"
_CLIENT_FIELD = re.compile(r"(\w+)=(.*?)(?= \w+=|$)")
_MARK = {"ok": "[ok]  ", "warn": "[warn]", "fail": "[FAIL]", "off": "[off] ", "unknown": "[??]  "}


@dataclass
class LogRecord:
    day: str
    time: str
    level: str
    logger: str
    message: str
    count: int = 1
    tail: str = ""       # a traceback's last line (the exception)


@dataclass
class ClientError:
    day: str
    time: str
    source: str
    message: str
    where: str


@dataclass
class Dump:
    text: str
    file_name: str
    summary: dict[str, Any]
    wrong: list[dict[str, str]] = field(default_factory=list)     # fail then warn rows: {state, title, detail}
    errors: list[LogRecord] = field(default_factory=list)         # newest first
    client_errors: list[ClientError] = field(default_factory=list)  # newest first


def _fold_key(logger: str, message: str) -> str:
    return logger + " " + re.sub(r"\d+(?:\.\d+)?", "#", message)[:200]


def parse_log(text: str, *, keep: int = ISSUE_REPORT_LOG_RECORDS) -> tuple[list[LogRecord], list[ClientError]]:
    """Warnings and errors from the engine log's text, oldest first, repeats folded into the newest;
    and the desk windows' error reports (logged by ``routes/client_errors.py``)."""
    folded: OrderedDict[str, LogRecord] = OrderedDict()
    clients: list[ClientError] = []
    current: LogRecord | None = None
    for line in text.splitlines():
        m = _RECORD_START.match(line)
        if m is None:
            # A traceback line: keep the last one, the exception itself.
            if current is not None and line.strip():
                current.tail = line.strip()[:ISSUE_REPORT_LOG_LINE_MAX]
            continue
        day, time_, level, logger, message = m.groups()
        current = None
        if level not in _WANTED:
            continue
        if logger == _CLIENT_LOGGER:
            if message.startswith("client_error "):
                fields = dict(_CLIENT_FIELD.findall(message[len("client_error "):]))
                clients.append(ClientError(day, time_, fields.get("source", "?"),
                                           fields.get("msg", "")[:ISSUE_REPORT_LOG_LINE_MAX],
                                           fields.get("url", "")[:200]))
            continue
        key = _fold_key(logger, message)
        record = folded.pop(key, None)
        count = record.count + 1 if record else 1
        current = LogRecord(day, time_, level, logger, message[:ISSUE_REPORT_LOG_LINE_MAX], count)
        folded[key] = current
    records = list(folded.values())[-keep:]
    return records, clients[-ISSUE_REPORT_CLIENT_ERRORS:]


def _when(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, _ET)


def file_name(now: float) -> str:
    return f"nova-dump-{_when(now).strftime('%Y-%m-%d-%H%M')}.txt"


def render_dump(*, diag: dict[str, Any] | None, diag_error: str | None, records: list[LogRecord],
                log_error: str | None, client_errors: list[ClientError], windows: list[dict[str, Any]],
                context_lines: list[str], now: float, scrubber: Scrubber, windows_error: str | None = None) -> Dump:
    s = scrubber.text
    rows = list((diag or {}).get("rows") or [])
    counts = {state: sum(1 for r in rows if r.get("state") == state) for state in _MARK}
    wrong = [{"state": str(r.get("state")), "title": s(str(r.get("title") or "")), "detail": s(str(r.get("detail") or ""))}
             for state in ("fail", "warn") for r in rows if r.get("state") == state]
    lines = [
        f"Nova desk dump -- {_when(now).strftime('%Y-%m-%d %H:%M:%S ET')} (schema {ISSUE_REPORT_DUMP_SCHEMA_VERSION})",
        "Built for a public page: API keys, tokens, IBKR account numbers, balances and P&L, file paths,",
        "the user and machine names, e-mail and IP addresses are removed.",
        "",
        "## Summary",
        *[f"- {s(line)}" for line in context_lines],
        f"- Checklist: {len(rows)} rows -- " + ", ".join(f"{counts[k]} {k}" for k in ("fail", "warn", "unknown", "off", "ok")),
        f"- Engine log: {len(records)} distinct warnings / errors" + (f" (unreadable: {s(log_error)})" if log_error else ""),
        f"- Desk windows: {len(windows)} reporting, {len(client_errors)} errors reported",
    ]
    if wrong:
        lines += ["", "What looks wrong:"] + [f"  {_MARK[w['state']]} {w['title']}: {w['detail']}" for w in wrong]
    lines += ["", "## Desk checklist"]
    if diag is None:
        lines.append(f"(the checklist could not be read: {s(diag_error or 'unknown error')})")
    titles = {g.get("id"): g.get("title") for g in (diag or {}).get("groups") or []}
    by_group: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in rows:
        by_group.setdefault(str(row.get("group")), []).append(row)
    for gid, group_rows in by_group.items():
        lines.append(f"### {titles.get(gid, gid)}")
        for row in group_rows:
            lines.append(f"{_MARK.get(str(row.get('state')), '[??]  ')} {s(str(row.get('title')))}: {s(str(row.get('detail')))}")
            if row.get("state") != "ok" and row.get("cause"):
                lines.append(f"       cause: {s(str(row['cause']))}")
            if row.get("since"):
                lines.append(f"       since: {_when(float(row['since'])).strftime('%H:%M:%S ET')}")
            evidence = row.get("evidence")
            if evidence and gid not in ISSUE_REPORT_PRIVATE_EVIDENCE_GROUPS:
                lines.append("       evidence: " + json.dumps(scrubber.value(evidence), default=str, sort_keys=True))
        lines.append("")
    lines += ["## Engine log -- latest warnings and errors (oldest first; x N = repeated)"]
    if not records:
        lines.append("(none)" if not log_error else f"(unreadable: {s(log_error)})")
    for r in records:
        repeat = f" x{r.count}" if r.count > 1 else ""
        lines.append(f"{r.day[5:]} {r.time} {r.level:<7} {r.logger}: {s(r.message)}{repeat}")
        if r.tail:
            lines.append(f"       {s(r.tail)}")
    lines += ["", "## Desk windows -- errors reported (oldest first)"]
    if not client_errors:
        lines.append("(none)")
    for c in client_errors:
        lines.append(f"{c.day[5:]} {c.time} {s(c.source)}: {s(c.message)}" + (f"  [{s(c.where)}]" if c.where else ""))
    lines += ["", "## Desk windows -- open now"]
    if windows_error:
        lines.append(f"(the focus sensor could not be read: {s(windows_error)})")
    elif not windows:
        lines.append("(no window has reported in the last minute)")
    for w in windows:
        facts = [f"page {w.get('page') or '-'}"]
        if w.get("tab"):
            facts.append(f"tab {w['tab']}")
        if w.get("symbol"):
            facts.append(f"symbol {w['symbol']}")
        if w.get("trader_tabs"):
            facts.append("trader tabs " + " ".join(map(str, w["trader_tabs"])))
        facts.append("in front" if w.get("focused") else "behind")
        if w.get("minimized"):
            facts.append("minimized")
        if w.get("ui_tag"):
            facts.append(str(w["ui_tag"]))
        lines.append(f"- {s(str(w.get('window_id')))} ({w.get('role')}): " + s(", ".join(facts)))
    text = "\n".join(lines).rstrip() + "\n"
    if len(text) > ISSUE_REPORT_DUMP_MAX_CHARS:
        text = text[:ISSUE_REPORT_DUMP_MAX_CHARS] + "\n(cut: the dump is longer than the limit)\n"
    newest = [r for r in reversed(records) if r.level in ("ERROR", "CRITICAL")] or list(reversed(records))
    errors = [LogRecord(r.day, r.time, r.level, r.logger, s(r.message), r.count) for r in newest]
    clients = [ClientError(c.day, c.time, s(c.source), s(c.message), "") for c in reversed(client_errors)]
    summary = {
        "rows": len(rows),
        "fail": counts["fail"],
        "warn": counts["warn"],
        "unknown": counts["unknown"],
        "log_records": len(records),
        "client_errors": len(client_errors),
        "windows": len(windows),
        "checklist_error": s(diag_error) if diag is None and diag_error else None,
        "log_error": s(log_error) if log_error else None,
        "removed": scrubber.count,
    }
    return Dump(text=text, file_name=file_name(now), summary=summary, wrong=wrong, errors=errors,
                client_errors=clients)
