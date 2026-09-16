"""Parse Nasdaq Trade Halt RSS XML (official feed -- never HTML scrape).

Feed: https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts
Documented variants: http:// (301s to https), ``?feed=tradehalts&haltdate=MM/DD/YYYY``.
Poll at most once per minute (channel ``ttl`` is 1).

Authoritative item fields are the ``http://www.nasdaqtrader.com/`` children
(IssueSymbol, HaltDate, HaltTime, ReasonCode, PauseThresholdPrice,
ResumptionDate, ResumptionQuoteTime, ResumptionTradeTime). An HTML
``<description>`` table is ignored. Plain ``Key: Value`` description text
is a documented fallback when those children are missing.

Empty resume / threshold fields stay None -- never invent times.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from constants import (
    NASDAQ_TRADE_HALT_RSS_NS,
    NASDAQ_TRADE_HALT_RSS_URL,
    NASDAQ_TRADE_HALT_RSS_URL_HTTP,
    NASDAQ_TRADE_HALT_RSS_HALTDATE_PARAM,
)

ET = ZoneInfo("America/New_York")

# Market-wide circuit breaker Level 1/2/3 -- not per-symbol LULD tier.
MWCB_LEVELS = {"MWC1": 1, "MWC2": 2, "MWC3": 3}

_NS_RE = re.compile(r"^\{[^}]*\}")
_KV_RE = re.compile(
    r"(Issue Symbol|Halt Date|Halt Time|Reason Code|"
    r"Pause Threshold Price|Resumption Date|"
    r"Resumption Quote Time|Resumption Trade Time)\s*:\s*(.*)",
    re.IGNORECASE,
)
_DATE_FMTS = ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y")
_TIME_FMTS = ("%H:%M:%S", "%H:%M")

# Re-export documented URLs so tests / docs can cite one module.
RSS_URL = NASDAQ_TRADE_HALT_RSS_URL
RSS_URL_HTTP = NASDAQ_TRADE_HALT_RSS_URL_HTTP
RSS_HALTDATE_PARAM = NASDAQ_TRADE_HALT_RSS_HALTDATE_PARAM
RSS_NS = NASDAQ_TRADE_HALT_RSS_NS


@dataclass(frozen=True)
class HaltRssRow:
    symbol: str
    reason_code: str | None
    official_halt_start: float | None
    pause_threshold: str | None
    quote_resume: float | None
    trade_resume: float | None
    mwcb_level: int | None


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def normalize_symbol(raw: str | None) -> str:
    return (raw or "").strip().upper().replace(" ", "")


def mwcb_level(reason_code: str | None) -> int | None:
    if not reason_code:
        return None
    return MWCB_LEVELS.get(reason_code.strip().upper())


def parse_et_datetime(date_s: str | None, time_s: str | None) -> float | None:
    """Halt / resume stamps are US/Eastern. Incomplete pairs stay None."""
    if not date_s or not time_s:
        return None
    date_s = date_s.strip()
    time_s = time_s.strip().split(".", 1)[0]
    if not date_s or not time_s:
        return None
    parsed_date = None
    for fmt in _DATE_FMTS:
        try:
            parsed_date = datetime.strptime(date_s, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        return None
    parsed_time = None
    for fmt in _TIME_FMTS:
        try:
            parsed_time = datetime.strptime(time_s, fmt).time()
            break
        except ValueError:
            continue
    if parsed_time is None:
        return None
    dt = datetime.combine(parsed_date, parsed_time, tzinfo=ET)
    return dt.timestamp()


def _text(el: ElementTree.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _child_map(item: ElementTree.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for child in item:
        name = _localname(child.tag)
        fields[name.lower()] = _text(child)
    return fields


def _description_kv(raw: str) -> dict[str, str]:
    """Plain Key: Value lines only. HTML tables are not a source."""
    if not raw or "<" in raw:
        return {}
    out: dict[str, str] = {}
    aliases = {
        "issue symbol": "issuesymbol",
        "halt date": "haltdate",
        "halt time": "halttime",
        "reason code": "reasoncode",
        "pause threshold price": "pausethresholdprice",
        "resumption date": "resumptiondate",
        "resumption quote time": "resumptionquotetime",
        "resumption trade time": "resumptiontradetime",
    }
    for line in raw.splitlines():
        match = _KV_RE.match(line.strip())
        if not match:
            continue
        key = aliases.get(match.group(1).strip().lower())
        if key:
            out[key] = match.group(2).strip()
    return out


def _blank(raw: str | None) -> str | None:
    text = (raw or "").strip()
    return text or None


def _row_from_fields(fields: dict[str, str], title: str) -> HaltRssRow | None:
    symbol = normalize_symbol(fields.get("issuesymbol") or title)
    reason = _blank(fields.get("reasoncode"))
    level = mwcb_level(reason)
    halt_date = _blank(fields.get("haltdate"))
    resume_date = _blank(fields.get("resumptiondate")) or halt_date
    official = parse_et_datetime(halt_date, _blank(fields.get("halttime")))
    quote = parse_et_datetime(resume_date, _blank(fields.get("resumptionquotetime")))
    trade = parse_et_datetime(resume_date, _blank(fields.get("resumptiontradetime")))
    if not symbol and level is None:
        return None
    return HaltRssRow(
        symbol=symbol,
        reason_code=reason,
        official_halt_start=official,
        pause_threshold=_blank(fields.get("pausethresholdprice")),
        quote_resume=quote,
        trade_resume=trade,
        mwcb_level=level,
    )


def parse_trade_halt_rss(xml_text: str) -> dict[str, Any]:
    """Parse a recorded or live RSS body. Never raises on bad XML."""
    if not xml_text or not str(xml_text).strip():
        return {"ok": False, "rows": [], "mwcb": None, "error": "empty"}
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        return {"ok": False, "rows": [], "mwcb": None, "error": f"xml: {exc}"}
    if _localname(root.tag).lower() != "rss":
        return {"ok": False, "rows": [], "mwcb": None, "error": "not_rss"}

    rows: list[HaltRssRow] = []
    mwcb: dict[str, Any] | None = None
    for item in root.iter():
        if _localname(item.tag) != "item":
            continue
        fields = _child_map(item)
        title = fields.get("title") or _text(item.find("title"))
        desc = fields.get("description") or ""
        if "issuesymbol" not in fields or not fields.get("issuesymbol"):
            fields = {**_description_kv(desc), **fields}
        row = _row_from_fields(fields, title)
        if row is None:
            continue
        if row.mwcb_level is not None:
            if mwcb is None or row.mwcb_level > int(mwcb["level"]):
                mwcb = {
                    "level": row.mwcb_level,
                    "reason_code": row.reason_code,
                    "source": "nasdaq_trade_halt_rss",
                }
            continue
        if not row.symbol:
            continue
        rows.append(row)

    return {"ok": True, "rows": rows, "mwcb": mwcb, "error": None}


def row_to_overlay(row: HaltRssRow | None, *, status: str) -> dict[str, Any]:
    if row is None:
        return {
            "status": status,
            "matched": False,
            "reason_code": None,
            "pause_threshold": None,
            "official_halt_start": None,
            "quote_resume": None,
            "trade_resume": None,
        }
    return {
        "status": status,
        "matched": True,
        "reason_code": row.reason_code,
        "pause_threshold": row.pause_threshold,
        "official_halt_start": row.official_halt_start,
        "quote_resume": row.quote_resume,
        "trade_resume": row.trade_resume,
    }
