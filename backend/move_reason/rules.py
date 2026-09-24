"""Why it's moving (ADR 028): the checks and the likely cause, from facts. Pure: no I/O, no clock.

``read(facts)`` answers ``{likely, checks}``. Each check is ``yes`` / ``no`` / ``unknown`` with the value
that decided it and where it came from; an unknown fact stays unknown. The likely cause is the first of

  not_moving          under ``MOVE_MIN_CHANGE`` either way
  news_pending        halted for news, the release still to come
  news                a catalyst or dilution since the prior close
  short_squeeze       up; shorts heavy (20% of float or 3 days to cover) and borrow stressed
                      (a 50% fee, a fee doubled since the open, lendable shares gone or scarce), on volume
  routine_news        only a routine company item came out
  split_squeeze       up; a reverse split in the last ten days, a low float, the float turned over 3x
  low_float_momentum  up; a low float turned over 3x, no news
  thin_trading        below the usual volume (or, RVOL unknown, under a tenth of the float)
  unexplained         none of the above

and says ``possible`` rather than ``likely`` when the news was not read or a deciding fact is unknown.
A squeeze is never called from price alone: without short interest and borrow data it is not a candidate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from constants_move_reason import (
    MOVE_BORROW_AVAILABLE_DROP,
    MOVE_BORROW_FEE_HIGH,
    MOVE_BORROW_FEE_JUMP,
    MOVE_BORROW_FEE_JUMP_MIN,
    MOVE_BORROW_SCARCE_SHARES,
    MOVE_CONFIDENCE_LIKELY,
    MOVE_CONFIDENCE_POSSIBLE,
    MOVE_DAYS_TO_COVER_HIGH,
    MOVE_KIND_LOW_FLOAT_MOMENTUM,
    MOVE_KIND_NEWS,
    MOVE_KIND_NEWS_PENDING,
    MOVE_KIND_NOT_MOVING,
    MOVE_KIND_ROUTINE_NEWS,
    MOVE_KIND_SHORT_SQUEEZE,
    MOVE_KIND_SPLIT_SQUEEZE,
    MOVE_KIND_THIN_TRADING,
    MOVE_KIND_UNEXPLAINED,
    MOVE_LOW_FLOAT_SHARES,
    MOVE_MIN_CHANGE,
    MOVE_ROTATION_HIGH,
    MOVE_ROTATION_SQUEEZE,
    MOVE_ROTATION_THIN,
    MOVE_RVOL_SQUEEZE,
    MOVE_RVOL_THIN,
    MOVE_SHORT_PCT_HIGH,
    MOVE_SPLIT_RECENT_DAYS,
    MOVE_STATE_NO,
    MOVE_STATE_UNKNOWN,
    MOVE_STATE_YES,
)

ET = ZoneInfo("America/New_York")
# The catalyst classes (constants_catalysts) as a trader says them.
_CATEGORY_WORDS = {
    "fda_regulatory": "FDA / regulatory", "clinical_data": "clinical data", "merger_acquisition": "merger / acquisition",
    "contract_partnership": "contract / partnership", "earnings_guidance": "earnings / guidance",
    "listing_financing": "listing / financing", "theme_pivot": "theme pivot", "product_news": "product news",
    "company_news": "company headline", "offering_dilution": "offering / dilution",
    "delisting_split": "delisting / reverse split",
}
_SOURCE_WORDS = {"edgar": "SEC", "globenewswire": "GlobeNewswire", "prnewswire": "PR Newswire", "newsfile": "Newsfile",
                 "fda": "FDA", "alpaca": "Alpaca", "finnhub": "Finnhub"}


def shares(n: float | None) -> str:
    if n is None:
        return "?"
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}K"
    return f"{n:.0f}"


def _times(x: float) -> str:
    return f"{x:,.0f}x" if x >= 10 else f"{x:.1f}x"


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v else None


def _check(cid: str, label: str, state: str, value: str | None, detail: str | None, source: str,
           as_of: float | None = None) -> dict[str, Any]:
    return {"id": cid, "label": label, "state": state, "value": value, "detail": detail, "source": source,
            "as_of": as_of}


# -- the checks ------------------------------------------------------------------------------------
def _news(v: dict | None, now: float | None) -> dict[str, Any]:
    src = "News verdict"
    if isinstance(v, dict) and v.get("sources_answered"):
        src += ": " + ", ".join(_SOURCE_WORDS.get(s, s) for s in v["sources_answered"])
    if not isinstance(v, dict) or v.get("verdict") in (None, "not_checked"):
        return _check("news", "Company news", MOVE_STATE_UNKNOWN, "Not read yet", None, src)
    if v.get("news_pending"):
        code = f" ({v['halt_code']})" if v.get("halt_code") else ""
        return _check("news", "Company news", MOVE_STATE_YES, f"Halted for news{code}", "The release is still to come", src, now)
    kind = v.get("verdict")
    if kind in ("catalyst", "negative"):
        word = _CATEGORY_WORDS.get(v.get("category") or "", v.get("category") or "news")
        strength = f" ({v['strength']})" if v.get("strength") else ""
        return _check("news", "Company news", MOVE_STATE_YES, f"{word[:1].upper()}{word[1:]}{strength}",
                      None, src, v.get("published_ts"))
    words = {"routine_only": "Routine company item only", "noise_only": "Only movers lists and market wraps",
             "none_found": "None since the prior close"}
    return _check("news", "Company news", MOVE_STATE_NO, words.get(kind, str(kind)), None, src, now)


def _headline(v: dict) -> str | None:
    title = str(v.get("title") or "").strip()
    if v.get("source") == "edgar" and " | " in title:
        title = title.split(" | ", 1)[1].strip()
    return title or None


def _halts(h: dict | None, now: float | None) -> dict[str, Any]:
    src = "Halt log: Nasdaq halts and IBKR"
    if not isinstance(h, dict):
        return _check("halts", "Halts today", MOVE_STATE_UNKNOWN, "Halt log unavailable", None, src)
    news, luld, vol, other = (int(h.get(k) or 0) for k in ("news", "luld", "volatility", "other"))
    parts = []
    if news:
        parts.append(f"halted for news {news}x")
    if luld:
        parts.append(f"LULD pause {luld}x")
    if vol:
        parts.append(f"volatility pause {vol}x")
    if other:
        parts.append(f"other halt {other}x")
    if not parts:
        return _check("halts", "Halts today", MOVE_STATE_NO, "None today", None, src, now)
    text = ", ".join(parts)
    return _check("halts", "Halts today", MOVE_STATE_YES, text[:1].upper() + text[1:], None, src, now)


def _float(f: float | None, contradicted: str | None = None) -> dict[str, Any]:
    """``contradicted`` is the reason Yahoo's own counts contradict the float (#532): the value reads
    "54K?" and the detail says why. The state is still the float's -- the check describes, it does not gate."""
    src = "Yahoo float (can lag a reverse split or a dilution)"
    if f is None:
        return _check("float", "Float", MOVE_STATE_UNKNOWN, "Unknown", None, src)
    low = f < MOVE_LOW_FLOAT_SHARES
    return _check("float", "Float", MOVE_STATE_YES if low else MOVE_STATE_NO,
                  f"{shares(f)}{'?' if contradicted else ''} shares{' -- low float' if low else ''}", contradicted, src)


def _rotation(rot: float | None, volume: float | None, f: float | None) -> dict[str, Any]:
    src = "Today's volume (IBKR) over the float"
    if rot is None:
        return _check("float_rotation", "Volume vs float", MOVE_STATE_UNKNOWN, "Unknown",
                      "Needs today's volume and the float", src)
    return _check("float_rotation", "Volume vs float", MOVE_STATE_YES if rot >= MOVE_ROTATION_HIGH else MOVE_STATE_NO,
                  f"Float traded {_times(rot)}", f"{shares(volume)} shares on a {shares(f)} float", src)


def _volume(rvol: float | None) -> dict[str, Any]:
    src = "Relative volume (the scanner's RVOL)"
    if rvol is None:
        return _check("volume", "Volume vs usual", MOVE_STATE_UNKNOWN, "Unknown", None, src)
    return _check("volume", "Volume vs usual", MOVE_STATE_YES if rvol >= MOVE_RVOL_SQUEEZE else MOVE_STATE_NO,
                  f"RVOL {_times(rvol)}", None, src)


def _split(s: dict | None, now: float | None) -> dict[str, Any]:
    src = "Yahoo's last split"
    if not isinstance(s, dict):
        return _check("reverse_split", "Reverse split", MOVE_STATE_UNKNOWN, "Unknown", None, src)
    if not s.get("factor"):
        return _check("reverse_split", "Reverse split", MOVE_STATE_NO, "None on record", None, src)
    days = _num(s.get("days_ago"))
    when = f", {days:.0f} day{'s' if round(days) != 1 else ''} ago" if days is not None else ""
    if not s.get("reverse"):
        return _check("reverse_split", "Reverse split", MOVE_STATE_NO, f"Last split {s['factor']} (forward){when}", None, src)
    recent = days is not None and days <= MOVE_SPLIT_RECENT_DAYS
    return _check("reverse_split", "Reverse split", MOVE_STATE_YES if recent else MOVE_STATE_NO,
                  f"{_split_words(s['factor'])}{when}", "Fewer shares right after a split" if recent else None, src,
                  _num(s.get("ts")))


def _split_words(factor: str) -> str:
    a, _, b = str(factor).partition(":")
    return f"1-for-{b}" if a.strip() == "1" and b.strip() else f"{factor} split"


def _short(pct: float | None, dtc: float | None, si: float | None, as_of: float | None = None) -> dict[str, Any]:
    """``as_of`` is the FINRA settlement date Yahoo's short interest is from (#532). Days to cover is
    Yahoo's short ratio -- short interest over Yahoo's average volume, not FINRA's figure -- and says so."""
    src = ("FINRA short interest via Yahoo (twice a month, about two weeks late); "
           "days to cover is Yahoo's short ratio, over Yahoo's average volume")
    if pct is None and dtc is None:
        return _check("short_interest", "Short interest", MOVE_STATE_UNKNOWN, "Unknown", None, src)
    heavy = (pct is not None and pct >= MOVE_SHORT_PCT_HIGH) or (dtc is not None and dtc >= MOVE_DAYS_TO_COVER_HIGH)
    parts = []
    if pct is not None:
        parts.append(f"{pct * 100:.0f}% of float")
    if dtc is not None:
        parts.append(("under 0.1 days to cover" if dtc < 0.1 else f"{dtc:.1f} days to cover") + " (Yahoo ratio)")
    detail = None
    if si is not None:
        detail = f"{shares(si)} shares short" + (f", FINRA settlement {_day(as_of)}" if as_of is not None else "")
    return _check("short_interest", "Short interest", MOVE_STATE_YES if heavy else MOVE_STATE_NO, " · ".join(parts),
                  detail, src, as_of)


def _day(ts: float) -> str:
    """Aug 31: a settlement date, which Yahoo stamps at midnight UTC."""
    d = datetime.fromtimestamp(ts, timezone.utc)
    return f"{d:%b} {d.day}"


def _borrow(b: dict | None) -> dict[str, Any]:
    src = "IBKR short-stock availability (every 15 min)"
    if not isinstance(b, dict):
        return _check("borrow", "Borrow (IBKR)", MOVE_STATE_UNKNOWN, "Not recorded yet", None, src)
    as_of = _num(b.get("as_of"))
    opened = b.get("open") if isinstance(b.get("open"), dict) and b["open"].get("listed") else None
    since = f"since {_clock(opened.get('as_of'))}" if opened else ""
    open_words = _borrow_words(opened.get("fee_rate"), opened.get("available"), False) if opened else ""
    if not b.get("listed"):
        detail = f"{since[:1].upper()}{since[1:]} it had {_lc(open_words)}" if opened else None
        return _check("borrow", "Borrow (IBKR)", MOVE_STATE_YES, "Nothing to lend", detail, src, as_of)
    fee, avail, capped = _num(b.get("fee_rate")), _num(b.get("available")), bool(b.get("available_capped"))
    now_words = _borrow_words(fee, avail, capped)
    reasons = []
    if fee is not None and fee >= MOVE_BORROW_FEE_HIGH:
        reasons.append("expensive")
    f0 = _num(opened.get("fee_rate")) if opened else None
    if fee is not None and f0 and fee >= MOVE_BORROW_FEE_JUMP_MIN and fee >= MOVE_BORROW_FEE_JUMP * f0:
        reasons.append(f"fee {f0:.0f}% -> {fee:.0f}% {since}")
    a0 = _num(opened.get("available")) if opened else None
    if avail is not None and a0 and not capped and avail <= (1 - MOVE_BORROW_AVAILABLE_DROP) * a0:
        reasons.append(f"lendable {shares(a0)} -> {shares(avail)} {since}")
    if avail is not None and not capped and avail < MOVE_BORROW_SCARCE_SHARES:
        reasons.append("scarce")
    # The day's first reading is worth a line only when it differs from now.
    moved = f"At {_clock(opened.get('as_of'))}: {_lc(open_words)}" if opened and open_words != now_words else None
    detail = "; ".join(r for r in reasons if " -> " in r) or moved
    return _check("borrow", "Borrow (IBKR)", MOVE_STATE_YES if reasons else MOVE_STATE_NO, now_words, detail, src, as_of)


def _lc(text: str) -> str:
    return text[:1].lower() + text[1:]


def _clock(ts: Any) -> str:
    """04:05 ET, the time of the day's first borrow reading (the open unless the backend started later)."""
    t = _num(ts)
    return datetime.fromtimestamp(t, ET).strftime("%H:%M ET") if t is not None else "the open"


def _borrow_words(fee: Any, avail: Any, capped: bool) -> str:
    fee_n, avail_n = _num(fee), _num(avail)
    fee_s = f"fee {fee_n:.1f}%/yr" if fee_n is not None else "fee ?"
    avail_s = f"{'>' if capped else ''}{shares(avail_n)} shares to lend" if avail_n is not None else "? to lend"
    return f"{fee_s[:1].upper()}{fee_s[1:]} · {avail_s}"


# -- the read --------------------------------------------------------------------------------------
def read(facts: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    change = _num(facts.get("change_pct"))
    volume, f = _num(facts.get("volume")), _num(facts.get("float_shares"))
    rvol = _num(facts.get("rel_volume"))
    rot = volume / f if volume is not None and f else None
    si = _num(facts.get("short_interest"))
    pct = _num(facts.get("short_pct_float"))
    if pct is None and si is not None and f:
        pct = si / f
    dtc = _num(facts.get("days_to_cover"))
    contradicted = ((facts.get("float_contradicted_reason") or "Yahoo's own share counts contradict this float")
                    if facts.get("float_contradicted") is True else None)
    checks = [_news(facts.get("catalyst"), now), _halts(facts.get("halts"), now), _float(f, contradicted),
              _rotation(rot, volume, f), _volume(rvol), _split(facts.get("split"), now),
              _short(pct, dtc, si, _num(facts.get("short_interest_ts"))), _borrow(facts.get("borrow"))]
    by = {c["id"]: c for c in checks}
    return {"likely": _likely(change, by, rot, rvol, facts.get("catalyst")), "checks": checks,
            "derived": {"float_rotation": rot, "short_pct_float": pct}}


def _is(by: dict, cid: str, state: str = MOVE_STATE_YES) -> bool:
    return by[cid]["state"] == state


def _likely(change: float | None, by: dict, rot: float | None, rvol: float | None, verdict: Any) -> dict[str, Any]:
    news_known = not _is(by, "news", MOVE_STATE_UNKNOWN)
    conf = MOVE_CONFIDENCE_LIKELY if news_known else MOVE_CONFIDENCE_POSSIBLE
    tail = "" if news_known else " -- news not read yet"
    if change is None:
        return _cause(MOVE_KIND_UNEXPLAINED, "No price change on record", None, MOVE_CONFIDENCE_POSSIBLE)
    if abs(change) < MOVE_MIN_CHANGE:
        return _cause(MOVE_KIND_NOT_MOVING, f"Not a big move today ({change * 100:+.1f}%)", None, MOVE_CONFIDENCE_LIKELY)
    v = verdict if isinstance(verdict, dict) else {}
    up = change > 0
    squeeze = up and _is(by, "short_interest") and _is(by, "borrow") and (
        (rot is not None and rot >= MOVE_ROTATION_SQUEEZE) or (rvol is not None and rvol >= MOVE_RVOL_SQUEEZE))
    evidence = _evidence(by, ("float_rotation", "short_interest", "borrow", "reverse_split", "halts"))
    if v.get("news_pending"):
        return _cause(MOVE_KIND_NEWS_PENDING, "Halted for news -- the release is still to come", evidence, MOVE_CONFIDENCE_LIKELY)
    if v.get("verdict") in ("catalyst", "negative"):
        label = f"Company news: {by['news']['value'].lower()}" + (" -- with short-squeeze pressure" if squeeze else "")
        return _cause(MOVE_KIND_NEWS, label, _headline(v), MOVE_CONFIDENCE_LIKELY)
    if squeeze:
        after_split = (f" after a {by['reverse_split']['value'].split(',')[0]} reverse split"
                       if _is(by, "reverse_split") else "")
        return _cause(MOVE_KIND_SHORT_SQUEEZE,
                      "Likely short squeeze" + after_split + (" -- no company news" if news_known else tail), evidence, conf)
    low_float, turned = _is(by, "float"), rot is not None and rot >= MOVE_ROTATION_HIGH
    if v.get("verdict") == "routine_only":
        label = "Routine company item" + (" on a low float" if up and low_float and turned else "")
        return _cause(MOVE_KIND_ROUTINE_NEWS, label, _headline(v), MOVE_CONFIDENCE_LIKELY)
    if up and low_float and turned and _is(by, "reverse_split"):
        label = f"Supply squeeze after a {by['reverse_split']['value'].split(',')[0]} reverse split"
        label += " -- nothing to lend" if by["borrow"]["value"] == "Nothing to lend" else ""
        return _cause(MOVE_KIND_SPLIT_SQUEEZE, label + tail, evidence, conf)
    if up and low_float and turned:
        label = "Low-float momentum" + (" -- no company news" if news_known else tail)
        label += "; borrow is tight" if _is(by, "borrow") else ""
        return _cause(MOVE_KIND_LOW_FLOAT_MOMENTUM, label, evidence, conf)
    # Thin is below the usual volume; the float's turnover decides only when RVOL is unknown (a 62M float
    # can trade 3% of itself on 2.4x its usual volume -- TLSA 2026-09-23 -- and that is not thin).
    if (rvol is not None and rvol < MOVE_RVOL_THIN) or (rvol is None and rot is not None and rot < MOVE_ROTATION_THIN):
        return _cause(MOVE_KIND_THIN_TRADING, "Thin trading: the move rests on little volume" + tail, evidence, conf)
    unknowns = [c["label"].lower() for c in by.values() if c["state"] == MOVE_STATE_UNKNOWN]
    detail = f"Unknown: {', '.join(unknowns)}" if unknowns else evidence
    return _cause(MOVE_KIND_UNEXPLAINED, "No cause found in the data" + tail, detail,
                  MOVE_CONFIDENCE_POSSIBLE if unknowns else conf)


def _evidence(by: dict, ids: tuple[str, ...]) -> str | None:
    parts = [f"{by[i]['label']}: {by[i]['value']}" for i in ids if by[i]["state"] == MOVE_STATE_YES and by[i]["value"]]
    return "; ".join(parts) or None


def _cause(kind: str, label: str, detail: str | None, confidence: str) -> dict[str, Any]:
    return {"kind": kind, "label": label, "detail": detail, "confidence": confidence}
