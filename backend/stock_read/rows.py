"""The read's rows for the market facts (ADR 036): in play, front side, float, halts. Pure.

A row is ``{id, label, value, detail, state, source, as_of}``; ``state`` reads for a long momentum
trade -- ``ok``, ``warn``, ``bad`` -- or ``unknown`` (Nova does not know; the detail says why) or
``info`` (a fact that is neither). Every unknown says why; none is a pass.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_FLOAT_BAD,
    STOCK_READ_FLOAT_OK,
    STOCK_READ_HOD_FAR_PCT,
    STOCK_READ_HOD_NEAR_PCT,
    STOCK_READ_HOD_STALE_MIN,
    STOCK_READ_ROTATION_OK,
    STOCK_READ_ROUND_NEAR_PCT,
    STOCK_READ_RVOL_OK,
    STOCK_READ_RVOL_WARN,
    STOCK_READ_SPLIT_RECENT_DAYS,
    STOCK_READ_VOLUME_PROFILE_BARS,
)

ET = ZoneInfo("America/New_York")


def row(rid: str, label: str, value: str, state: str, source: str, detail: str | None = None,
        as_of: float | None = None) -> dict[str, Any]:
    return {"id": rid, "label": label, "value": value, "detail": detail, "state": state, "source": source,
            "as_of": as_of}


def hhmm(ts: float | None) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M") if ts else "--"


def shares(n: float | None) -> str:
    if n is None:
        return "--"
    n = float(n)
    for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}".replace(".0", "")
    return f"{n:.0f}"


def _humanize_gate(reason: str) -> str:
    if reason.startswith("master_liquidity:volume") or reason.startswith("master_liquidity:no_volume"):
        return "under the tradeable floor's volume"
    if reason.startswith("master_liquidity:price"):
        return "under the tradeable floor's price"
    if reason.startswith("master_liquidity:rvol"):
        return "under the tradeable floor's relative volume"
    if reason.startswith("master_surge"):
        return "no surge the master gate asks for"
    if reason == "blocklist":
        return "on the HOD Momo blocklist"
    return reason


def _humanize_block(reason: str) -> str:
    if reason.startswith("hod("):
        return "not at a new high of day"
    if reason.startswith("approach:below_hod"):
        return "not near the high of day"
    if reason.startswith("surge:"):
        return "not surging fast enough"
    if reason == "disabled":
        return "switched off"
    if reason.startswith("float"):
        return "its float rule"
    return reason.split("(")[0].replace("_", " ")


# -- in play -------------------------------------------------------------------------------------
def in_play_rows(f: dict[str, Any], history: dict[str, Any] | None) -> list[dict[str, Any]]:
    why = f.get("why") or {}
    facts = why.get("facts") or {}
    hod = f.get("hod_momo")
    out = [_hod_today(hod), _hod_now(hod), _catalyst(facts.get("catalyst")), _likely(why.get("likely")),
           _pillars(facts), _rvol(f.get("rvol"), facts), _board(f.get("board")), _ran_before(history)]
    return out


def _hod_today(hod: dict[str, Any] | None) -> dict[str, Any]:
    src = "HOD Momo alerts today"
    if hod is None:
        return row("hod_today", "HOD Momo today", "Not known", "unknown", src, "HOD Momo could not be read")
    if not hod["count"]:
        state = "warn" if hod.get("followed") else "unknown"
        detail = None if hod.get("followed") else "HOD Momo is not following it right now"
        return row("hod_today", "HOD Momo today", "No alert today", state, src, detail)
    first = (hod.get("firsts") or [{}])[0]
    by = " · ".join(f"{name} {n}" for name, n in sorted(hod["by_strategy"].items(), key=lambda kv: -kv[1]))
    detail = f"{by}. First: {hhmm(first.get('ts'))} at {first.get('price')}."
    return row("hod_today", "HOD Momo today", f"{hod['count']} alert{'s' if hod['count'] != 1 else ''} since "
               f"{hhmm(first.get('ts'))}", "ok", src, detail, hod.get("last_ts"))


def _hod_now(hod: dict[str, Any] | None) -> dict[str, Any]:
    src = "HOD Momo's last decision on it"
    dec = (hod or {}).get("decision")
    if not dec:
        return row("hod_now", "HOD Momo now", "No decision this session", "unknown", src,
                   "HOD Momo has not read a trade on it since Nova started")
    if dec.get("gate_blocked"):
        return row("hod_now", "HOD Momo now", "Gate refused", "bad", src, _humanize_gate(str(dec["gate_blocked"])),
                   dec.get("ts"))
    strategies = [s for s in dec.get("strategies") or [] if s.get("blocked_by") != "disabled"]
    firing = [s for s in strategies if s.get("passed")]
    if firing:
        names = ", ".join(s.get("name") or "?" for s in firing)
        return row("hod_now", "HOD Momo now", f"{len(firing)} of {len(strategies)} would fire", "ok", src, names,
                   dec.get("ts"))
    reasons = sorted({_humanize_block(str(s.get("blocked_by") or "")) for s in strategies})
    return row("hod_now", "HOD Momo now", f"Gate passed · 0 of {len(strategies)} would fire", "warn", src,
               "Every strategy: " + "; ".join(reasons[:3]) if reasons else None, dec.get("ts"))


_CATALYST_STATE = {"catalyst": "ok", "negative": "bad", "routine_only": "warn", "noise_only": "warn",
                   "none_found": "warn", "not_checked": "unknown"}


def _catalyst(v: dict[str, Any] | None) -> dict[str, Any]:
    src = "Catalyst verdict (news since the prior close)"
    if not v:
        return row("catalyst", "Catalyst", "Not read yet", "unknown", src, "No news source has read it yet")
    verdict = str(v.get("verdict") or "not_checked")
    cat = str(v.get("category") or "").replace("_", " ")
    value = {"catalyst": f"{cat or 'catalyst'} · {v.get('strength') or ''}".strip(" ·"),
             "negative": f"negative: {cat}", "routine_only": "routine items only", "noise_only": "no company news",
             "none_found": "none found", "not_checked": "not checked"}.get(verdict, verdict)
    detail = None
    if v.get("title"):
        detail = f"{hhmm(v.get('published_ts'))}, {v.get('source') or '?'}: \"{v['title']}\""
    if v.get("news_pending"):
        detail = "A news halt is open: the news is pending. " + (detail or "")
    return row("catalyst", "Catalyst", value[:1].upper() + value[1:], _CATALYST_STATE.get(verdict, "unknown"), src,
               detail, v.get("published_ts"))


_LIKELY_STATE = {"news": "ok", "short_squeeze": "ok", "split_squeeze": "ok", "low_float_momentum": "ok",
                 "news_pending": "warn", "routine_news": "warn", "thin_trading": "warn", "unexplained": "warn",
                 "not_moving": "info"}


def _likely(likely: dict[str, Any] | None) -> dict[str, Any]:
    src = "Why it's moving (rules)"
    if not likely:
        return row("why", "Why it's moving", "Not known", "unknown", src, "The read could not be made")
    state = _LIKELY_STATE.get(str(likely.get("kind")), "info")
    if likely.get("confidence") == "possible" and state == "ok":
        state = "warn"
    return row("why", "Why it's moving", f"{likely.get('label')} ({likely.get('confidence')})", state, src,
               likely.get("detail"))


def _pillars(facts: dict[str, Any]) -> dict[str, Any]:
    from strategy.five_pillars import evaluate_five_pillars

    ch = facts.get("change_pct")
    res = evaluate_five_pillars({
        "symbol": facts.get("symbol"), "price": facts.get("price"),
        # The graders read percent past 1.0: +114.8% is 114.8, never the fraction 1.148 (AGENTS §3).
        "change_pct": None if ch is None else ch * 100.0, "rel_volume": facts.get("rel_volume"),
        "catalyst": facts.get("catalyst"), "float": facts.get("float_shares"),
        "float_contradicted": facts.get("float_contradicted"),
    }).to_dict()
    n, total = res.get("pass_count", 0), res.get("total", 5)
    failed = [p for p in res.get("pillars") or [] if not p.get("passed")]
    value = f"{n} of {total}" + (f" -- {failed[0].get('detail')}" if len(failed) == 1 else "")
    detail = " · ".join(f"{p['name'].replace('_', ' ')} {'✓' if p['passed'] else '✗'} {p['detail']}"
                        for p in res.get("pillars") or [])
    state = "ok" if n == total else ("warn" if n >= total - 2 else "bad")
    return row("pillars", "Five Pillars", value, state, "Five Pillars", detail)


def _rvol(rvol: dict[str, Any] | None, facts: dict[str, Any]) -> dict[str, Any]:
    src = "Relative volume (today's pace vs the average day)"
    pace = (rvol or {}).get("rvol_vs_adv_pace") or facts.get("rel_volume")
    if pace is None:
        return row("rvol", "Relative volume", "Not known", "unknown", src, "No average volume on file for it")
    five = (rvol or {}).get("rvol_5min")
    value = f"{pace:,.0f}x" + (f" · 5-min {five:,.0f}x" if five is not None else "")
    state = "ok" if pace >= STOCK_READ_RVOL_OK else ("warn" if pace >= STOCK_READ_RVOL_WARN else "bad")
    adv = (rvol or {}).get("average_volume")
    detail = f"Today {shares((rvol or {}).get('day_volume') or facts.get('volume'))} against an average day of " \
             f"{shares(adv)}. Time-of-day RVOL is not stored." if adv else None
    return row("rvol", "Relative volume", value, state, src, detail)


def _board(source: str | None) -> dict[str, Any]:
    src = "The scanner boards now"
    if source in (None, "quote"):
        return row("board", "On the boards", "Not on a board", "info", src)
    return row("board", "On the boards", f"On {source.replace('_', ' ').title()}", "ok", src)


def _ran_before(history: dict[str, Any] | None) -> dict[str, Any]:
    src = "Stored daily bars (a run: a high 40%+ over the prior close)"
    if history is None or not history.get("daily_days"):
        return row("ran_before", "Has it run before?", "Not known", "unknown", src, "No daily bars stored for it")
    runs = [r for r in history.get("runs") or [] if not r.get("today")]
    if not runs:
        return row("ran_before", "Has it run before?", f"No runs in {history['daily_days']} sessions", "info", src)
    faded = [r for r in runs[:2] if r["close_pct"] < r["run_pct"] / 2]
    detail = "; ".join(f"{r['date'][5:]} high +{r['run_pct'] * 100:.0f}% -> closed {r['close_pct'] * 100:+.0f}%"
                       for r in runs[:3])
    value = f"{len(runs)} run{'s' if len(runs) != 1 else ''} of +40% in {history['daily_days']} sessions"
    if len(faded) == min(2, len(runs)):
        value += "; faded"
    return row("ran_before", "Has it run before?", value, "warn" if faded else "info", src, detail)


# -- front side ----------------------------------------------------------------------------------
def front_rows(f: dict[str, Any], d: dict[str, Any]) -> list[dict[str, Any]]:
    """``d``: what the read derived -- price, levels, macd_1m (+ source), macd_5m, ema9, ema20,
    volume profile, backside warnings, now."""
    out = []
    m1 = d.get("macd_1m")
    if m1 is None:
        out.append(row("macd_1m", "MACD 1-minute", "Not known", "unknown", "1-minute bars",
                       "Fewer than 35 closed 1-minute candles"))
    else:
        out.append(row("macd_1m", "MACD 1-minute", f"hist {m1['macd_hist']:+.3f} · line {m1['macd_line']:+.3f}",
                       "ok" if m1["macd_hist"] > 0 else "bad", d.get("macd_1m_source") or "1-minute bars",
                       "Histogram = MACD - signal (12/26/9) on the last closed candle: the setup scanners arm only "
                       "above zero." + (" The line itself is under zero." if m1["macd_line"] < 0 else "")))
    m5 = d.get("macd_5m")
    if m5 is None:
        out.append(row("macd_5m", "MACD 5-minute", "Not known", "unknown", "5-minute bars",
                       "Fewer than 35 closed 5-minute candles"))
    else:
        out.append(row("macd_5m", "MACD 5-minute", f"hist {m5['macd_hist']:+.3f} · line {m5['macd_line']:+.3f}",
                       "ok" if m5["macd_hist"] > 0 else "bad", "5-minute bars",
                       "Nothing gates on the 5-minute MACD; the setup scanners read the 1-minute."))
    price = d.get("price")
    lv = d.get("levels") or {}
    vw = lv.get("vwap")
    if price is None or vw is None:
        out.append(row("vwap", "VWAP", "Not known", "unknown", "Session VWAP from 04:00 ET",
                       "No price or no volume today"))
    else:
        pct = price / vw - 1
        out.append(row("vwap", "VWAP", f"{'above' if price >= vw else 'under'} {vw:.2f} ({pct:+.1%})",
                       "ok" if price >= vw else "bad", "Session VWAP from 04:00 ET (the chart's)"))
    e9, e20 = d.get("ema9"), d.get("ema20")
    if price is None or e9 is None:
        out.append(row("ema", "9 / 20 EMA (1m)", "Not known", "unknown", "1-minute bars", "Too few candles"))
    else:
        above = [n for n, v in (("9", e9), ("20", e20)) if v is not None and price >= v]
        known = [n for n, v in (("9", e9), ("20", e20)) if v is not None]
        state = "ok" if len(above) == len(known) else ("bad" if not above else "warn")
        value = " · ".join(f"{'above' if price >= v else 'under'} {n} EMA {v:.2f}"
                           for n, v in (("9", e9), ("20", e20)) if v is not None)
        out.append(row("ema", "9 / 20 EMA (1m)", value, state, d.get("ema_source") or "1-minute bars",
                       "The setups' pullback and flag candles must close at or above the 9 EMA."))
    vp = d.get("volume_profile")
    if vp is None:
        out.append(row("volume_profile", "Volume on green vs red", "Not known", "unknown", "1-minute candles"))
    else:
        state = "ok" if vp["green"] > vp["red"] else ("warn" if vp["green"] == vp["red"] else "bad")
        out.append(row("volume_profile", "Volume on green vs red",
                       f"{shares(vp['green'])} vs {shares(vp['red'])}, last {vp['bars']}", state,
                       f"The last {STOCK_READ_VOLUME_PROFILE_BARS} closed 1-minute candles",
                       "Heavy volume on green candles and light on red is the healthy profile."))
    out.append(_hod_row(lv.get("hod"), price, d.get("now") or 0.0))
    out.append(_round_row(lv, price))
    warnings = d.get("backside") or []
    out.append(row("backside", "Backside warnings", f"{len(warnings)}: {warnings[0]}" if warnings else "None now",
                   "warn" if warnings else "ok", "The day's candles",
                   "; ".join(warnings) if warnings else "Topping tail at the high, the high candle the day's "
                   "biggest volume and red, MACD crossing under, a candle closing under the one before."))
    return out


def _hod_row(hod: dict[str, Any] | None, price: float | None, now: float) -> dict[str, Any]:
    src = "Today's 1-minute bars"
    if not hod or price is None:
        return row("hod", "High of day", "Not known", "unknown", src, "No bars today")
    under = 1 - price / hod["price"] if hod["price"] else 0.0
    age_min = (now - hod["ts"]) / 60.0 if now else None
    value = f"{hod['price']:.2f} at {hhmm(hod['ts'])}"
    if age_min is not None:
        value += f" · {int(age_min // 60)} h {int(age_min % 60)} m ago" if age_min >= 60 else f" · {age_min:.0f} m ago"
    if under <= STOCK_READ_HOD_NEAR_PCT:
        state = "ok"
    elif under >= STOCK_READ_HOD_FAR_PCT and (age_min or 0) >= STOCK_READ_HOD_STALE_MIN:
        state = "bad"
    else:
        state = "warn"
    return row("hod", "High of day", value, state, src, f"{under:.1%} under it", hod["ts"])


def _round_row(lv: dict[str, Any], price: float | None) -> dict[str, Any]:
    above, below = lv.get("round_above"), lv.get("round_below")
    if price is None or above is None:
        return row("round", "Next round numbers", "Not known", "unknown", "Price")
    near = (above - price) / price <= STOCK_READ_ROUND_NEAR_PCT
    return row("round", "Next round numbers", f"{above:.2f} ({above - price:+.2f}) · {below:.2f}",
               "warn" if near else "info", "Half and whole dollars",
               "A half or whole dollar just over the price often holds sellers." if near else None)


# -- float ---------------------------------------------------------------------------------------
def float_rows(f: dict[str, Any]) -> list[dict[str, Any]]:
    facts = ((f.get("why") or {}).get("facts")) or {}
    fl, vol = facts.get("float_shares"), facts.get("volume")
    src = "Yahoo fundamentals"
    out = []
    if fl is None:
        out.append(row("float", "Float", "Unknown", "unknown", src, "Yahoo gave none"))
    else:
        state = "ok" if fl < STOCK_READ_FLOAT_OK else ("warn" if fl < STOCK_READ_FLOAT_BAD else "bad")
        detail = None
        if facts.get("float_contradicted"):
            state, detail = "warn", facts.get("float_contradicted_reason") or "Yahoo's own counts contradict it"
        out.append(row("float", "Float", shares(fl) + ("?" if facts.get("float_contradicted") else ""), state, src,
                       detail))
    if fl and vol:
        rot = vol / fl
        out.append(row("rotation", "Float rotation", f"{rot:.1f}x today", "ok" if rot >= STOCK_READ_ROTATION_OK
                       else "info", "Today's volume over the float"))
    else:
        out.append(row("rotation", "Float rotation", "Unknown", "unknown", "Today's volume over the float",
                       "Needs the float" if not fl else "Needs today's volume"))
    split = facts.get("split")
    if not split:
        out.append(row("split", "Reverse split", "None on file", "info", "Yahoo's last split"))
    else:
        days = float(split.get("days_ago") or 0)
        recent = bool(split.get("reverse")) and days <= STOCK_READ_SPLIT_RECENT_DAYS
        out.append(row("split", "Reverse split" if split.get("reverse") else "Last split",
                       f"{split.get('factor')} · {days:.0f} days ago", "ok" if recent else "info", "Yahoo's last split",
                       "A recent reverse split shrank the share count." if recent else None, split.get("ts")))
    cat = facts.get("catalyst")
    if not cat:
        out.append(row("dilution", "Dilution today", "Not checked", "unknown", "Catalyst items",
                       "No news source has read it yet"))
    elif cat.get("verdict") == "negative" or cat.get("negative_too"):
        out.append(row("dilution", "Dilution today", "An offering or dilution item", "bad", "Catalyst items",
                       cat.get("title")))
    else:
        out.append(row("dilution", "Dilution today", "No offering in today's items", "ok", "Catalyst items"))
    return out


# -- halts ---------------------------------------------------------------------------------------
def halts_rows(f: dict[str, Any], d: dict[str, Any]) -> list[dict[str, Any]]:
    facts = ((f.get("why") or {}).get("facts")) or {}
    halted = f.get("halted")
    out = [row("halted", "Halted now", {True: "Yes", False: "No", None: "Not known"}[halted],
               {True: "bad", False: "ok", None: "unknown"}[halted], "IBKR's halt tick, else the Nasdaq halt feed",
               None if halted is not None else "No IBKR line has reported and the Nasdaq halt feed is not answering")]
    h = facts.get("halts")
    if h is None:
        out.append(row("halts_today", "Halts today", "Not known", "unknown", "The halt log",
                       "The halt log could not be read"))
    else:
        n = sum(int(h.get(k) or 0) for k in ("news", "luld", "volatility", "other"))
        parts = [f"{k} {h[k]}" for k in ("news", "luld", "volatility", "other") if h.get(k)]
        out.append(row("halts_today", "Halts today", "None" if not n else ", ".join(parts),
                       "ok" if not n else "warn", "The halt log (Nasdaq halts and IBKR)"))
    out.append(row("luld", "Limit up / down band", "Not computed", "unknown", "--",
                   "Nova has no source for the limit-up / limit-down bands yet"))
    med = d.get("median_range")
    out.append(row("candle", "Normal 1-minute candle", f"{med:.2f}" if med is not None else "Not known",
                   "info" if med is not None else "unknown", "The median range of the last 20 closed candles",
                   "A stop inside one normal candle is easy to shake out." if med is not None else None))
    bot = f.get("bot") or {}
    br = d.get("breakers")
    if br:
        out.append(row("breakers", "Loss breakers", f"bot trip {br['soft_usd']:+,.0f} · all-stop {br['hard_usd']:+,.0f}",
                       "info", f"The bot's breakers on {str(bot.get('venue') or '?').title()}"))
    return out
