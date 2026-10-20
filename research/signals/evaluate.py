"""One in-play stock-day's signals at the end of every minute from ``in_play_m`` through 15:59, by the Trader's own
rules: the facts as they stood at that minute are put in the shape the Signals panel's gather builds
(``backend/stock_read/gather.py``), and its pure rules read them -- ``stock_read.rows`` / ``read.derive`` /
``read._verdict``, ``plan_liquidity.read``, ``history.runs``, ``move_reason.rules.read``, ``catalysts.classify`` --
plus the setup lanes (``lanes.py``). Nothing here restates a rule; a fact with no history is passed as unknown.
"""
from __future__ import annotations

import bisect
from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import lanes
from inputs import DayInputs, ts_of
from market_reads import signals_store as ss
from market_reads.signal_registry import MINUTE_COLUMNS

ET = ZoneInfo("America/New_York")
HALT_LOG_FROM = "2021-09-21"
FLOAT_PROOF = 20_000_000         # FIVE_PILLARS_MAX_FLOAT: shares outstanding under it prove the float is too


def _bar_dicts(day: str, bars: pd.DataFrame) -> list[dict[str, float]]:
    return [{"t": ts_of(day, m), "o": o, "h": h, "l": lo, "c": c, "v": v} for m, o, h, lo, c, v in
            zip(bars["m"], bars["open"], bars["high"], bars["low"], bars["close"], bars["volume"], strict=True)]


def _bars(day: str, bars: pd.DataFrame) -> list:
    from setup_scanner.bars import Bar
    return [Bar(ts_of(day, m), float(o), float(h), float(lo), float(c), float(v)) for m, o, h, lo, c, v in
            zip(bars["m"], bars["open"], bars["high"], bars["low"], bars["close"], bars["volume"], strict=True)]


class Catalyst:
    """The classifier's verdict as of a moment: it changes only when an item is published, so it is judged again
    only then (the same answer as judging every minute)."""

    def __init__(self, day: str, items: list[dict], answered: list[str]):
        from catalysts import windows
        self.items, self.answered = items, answered
        self.start = windows.window_start(ts_of(day, 240))
        self.times = [float(it.get("published_ts") or 0.0) for it in items]
        self._key, self._value = None, None

    def at(self, now: float) -> dict[str, Any]:
        from catalysts.classify import verdict
        key = bisect.bisect_right(self.times, now)
        if key != self._key:
            self._key, self._value = key, verdict(self.items, window_start=self.start, cutoff=now,
                                                  sources_answered=self.answered)
        return self._value


def _hod(alerts: list[dict] | None, now: float) -> dict[str, Any] | None:
    """``gather._hod``'s shape from a rebuilt day's alerts raised by ``now``; None when the day was not rebuilt."""
    if alerts is None:
        return None
    seen = [a for a in alerts if a["ts"] <= now]
    by = Counter(str(a["strategy"]) for a in seen)
    firsts: dict[str, dict] = {}
    for a in seen:
        firsts.setdefault(str(a["strategy"]), {"ts": a["ts"], "price": a["price"], "strategy": a["strategy"]})
    return {"count": len(seen), "by_strategy": dict(by), "firsts": sorted(firsts.values(), key=lambda x: x["ts"]),
            "last_ts": seen[-1]["ts"] if seen else None, "followed": False, "decision": None}


def _halts(events: list[dict] | None, prior: list[dict] | None, symbol: str, now: float, day: str):
    """``(facts.halts, halted)`` at ``now``: the halt log's own counting; unknown before Nasdaq's log starts."""
    if events is None or day < HALT_LOG_FROM:
        return None, None
    from leaderboard.halts import halted_at
    from move_reason.facts import count_halts
    mine = [e for e in events if e.get("symbol") == symbol and float(e.get("ts") or 0) <= now]
    before = [e for e in (prior or []) if e.get("symbol") == symbol]
    return count_halts(mine, before), halted_at(mine, symbol, now)


def _float_for_desk(shares: float | None) -> float | None:
    """SEC's shares outstanding bound the float from above: under the pillar's limit they prove it; over it the float
    is not known (``day_movers.floats.proofs``'s rule)."""
    return shares if shares is not None and shares <= FLOAT_PROOF else None


def stock_day(inputs: DayInputs, info: dict[str, Any]) -> dict[str, list]:
    """``{column: [value per minute]}`` for ``m`` from ``in_play_m`` through ``LAST_M`` (and ``m`` itself)."""
    from market import pace_relative_volume
    from move_reason import rules as why_rules
    from stock_read import history as hist_mod
    from stock_read import plan_liquidity, read, rows
    from strategy.five_pillars import evaluate_five_pillars

    day, symbol = inputs.day, info["symbol"]
    bars = inputs.bars[symbol]
    rv = inputs.rvol.get(symbol)
    prev_close, adv = float(info["prev_close"]), info.get("day_avg_volume")
    minutes = list(range(int(info["in_play_m"]), ss.LAST_M + 1))
    ends = [ts_of(day, m + 1) for m in minutes]
    lane_states = lanes.run(day, symbol, _bars(day, bars), prev_close, ends)
    dicts = _bar_dicts(day, bars)
    bar_m = bars["m"].to_numpy()
    rv_m = rv["m"].to_numpy() if rv is not None else np.zeros(0, dtype=np.int64)
    cat = Catalyst(day, *inputs.catalysts.get(symbol, ([], [])))
    boards = inputs.boards.get(symbol, [])
    board_ts = [b[0] for b in boards]
    covered = set(inputs.board_minutes)
    shares = (inputs.floats.get(symbol) or {}).get("shares")
    daily = inputs.history.get(symbol, [])
    hist = {"daily_days": len(daily), "runs": hist_mod.runs(daily, day), "unfinished": []}
    ran_row = rows._ran_before(hist)
    runs_n = len([r for r in hist["runs"] if not r.get("today")])
    hod_alerts = inputs.hod.get(symbol, []) if inputs.hod is not None else None
    out: dict[str, list] = {c: [] for c in ("m", *MINUTE_COLUMNS)}
    for i, (m, now) in enumerate(zip(minutes, ends, strict=True)):
        k = int(np.searchsorted(bar_m, m, side="right"))
        so_far = dicts[:k]
        price = so_far[-1]["c"]
        j = int(np.searchsorted(rv_m, m, side="right")) - 1
        cum = float(rv["cum"].iat[j]) if j >= 0 else float(sum(b["v"] for b in so_far))
        base = rv["base"].iat[j] if j >= 0 else None
        vol5, base5 = (rv["vol5"].iat[j], rv["base5"].iat[j]) if j >= 0 else (None, None)
        rvol_cum = cum / float(base) if base and base > 0 else None
        rvol_5m = float(vol5) / float(base5) if base5 and base5 > 0 and vol5 is not None else None
        rvol_daily = cum / float(adv) if adv and adv > 0 else None
        pace = pace_relative_volume(cum, adv, datetime.fromtimestamp(now, ET))
        change = price / prev_close - 1.0
        verdict = cat.at(now)
        halts, halted = _halts(inputs.halt_events, inputs.halt_prior, symbol, now, day)
        facts = {"symbol": symbol, "price": price, "change_pct": change, "volume": cum, "rel_volume": pace,
                 "catalyst": verdict, "float_shares": _float_for_desk(shares), "float_contradicted": False,
                 "shares_issued": None, "split": None, "halts": halts, "short_interest": None, "borrow": None}
        why = why_rules.read(facts, now)
        b = bisect.bisect_right(board_ts, now - 60.0) - 1
        minute_ts = float(int((now - 60.0) // 60) * 60)
        board = boards[b][1] if b >= 0 and boards[b][0] == minute_ts else None
        f = {"symbol": symbol, "now": now, "bars": so_far, "bars5": [], "setups": None,
             "why": {"facts": facts, "likely": why["likely"]}, "hod_momo": _hod(hod_alerts, now),
             "rvol": {"rvol_vs_adv_pace": pace, "rvol_5min": rvol_5m, "average_volume": adv, "day_volume": cum},
             "board": board, "halted": halted, "luld": None, "dilution": None, "replay": False}
        d = read.derive(f)
        liquid = plan_liquidity.read({"bars": d["bars"], "volume": cum, "price": price}, now)
        in_play = rows.in_play_rows(f, None)[:-1] + [ran_row, plan_liquidity.row(liquid)]
        front = rows.front_rows(f, d)
        floats = rows.float_rows(f)
        halt_rows = rows.halts_rows(f, d)
        r = {x["id"]: x for x in (*in_play, *front, *floats, *halt_rows)}
        pillars = evaluate_five_pillars({
            "symbol": symbol, "price": price, "change_points": change * 100.0, "rel_volume": pace,
            "catalyst": verdict, "float": _float_for_desk(shares), "float_contradicted": False}).to_dict()
        passed = {p["name"]: bool(p["passed"]) for p in pillars["pillars"]}
        board_known = minute_ts in covered
        values = {
            "m": m, "price": price, "change_pct": change * 100.0, "rvol": rvol_cum, "rvol_5m": rvol_5m,
            "rvol_daily": rvol_daily, "rvol_pace": pace,
            "in_play": read._verdict("in_play", in_play, f, None)[1],
            "pillars": r["pillars"]["state"], "pillars_n": int(pillars["pass_count"]),
            "pillar_price": passed.get("price"), "pillar_change": passed.get("change_pct"),
            "pillar_rvol": passed.get("relative_volume"), "pillar_catalyst": passed.get("catalyst"),
            "pillar_float": passed.get("float"),
            "rvol_state": r["rvol"]["state"],
            "catalyst": verdict.get("verdict"), "catalyst_state": r["catalyst"]["state"],
            "why": (why["likely"] or {}).get("kind"), "why_state": r["why"]["state"],
            "board": board, "board_state": r["board"]["state"] if board_known else "unknown",
            "ran_before": ran_row["state"], "runs_n": runs_n,
            "liquidity": liquid.get("state"), "liquidity_day_usd": liquid.get("day_dollars"),
            "liquidity_5m_usd": liquid.get("pace_dollars"),
            "hod_today": r["hod_today"]["state"], "hod_alerts": f["hod_momo"]["count"] if f["hod_momo"] else None,
            "front": read._verdict("front", front, f, None)[1],
            "front_macd_1m": r["macd_1m"]["state"], "front_vwap": r["vwap"]["state"], "front_ema": r["ema"]["state"],
            "front_volume_profile": r["volume_profile"]["state"], "front_hod": r["hod"]["state"],
            "float": r["float"]["state"], "float_shares": shares, "rotation": r["rotation"]["state"],
            "halted": halted, "halts_today": r["halts_today"]["state"],
            "halts_n": sum(int(halts.get(k) or 0) for k in ("news", "luld", "volatility", "other")) if halts else None,
            "halts": read._verdict("halts", halt_rows, f, None)[1],
        }
        for column, states in lane_states.items():
            values[column] = states[i]
        for column in out:
            out[column].append(values.get(column))
    return out
