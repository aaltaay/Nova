"""The five-year test's simulation (ADR 049 section 12, step 4): the scanner's own short detectors and scoring on
minute bars, then gate 1's account. Pure: bars and rules in, trades and numbers out; nothing here reads a file.

``walk`` runs one stock-day the way a lane would have: the bars before the stock was followed seed the detector
at once (the seeder's 04:00 bars), then each minute's open and its extreme are fed as live prices (the low for a
breakdown, the high for the SSR bounce) and the minute closes. A trigger opens a trade scored by
``setup_scanner.scoring.ScoreTracker`` on the bars that follow; one trade at a time on a stock.

``account`` sizes and costs the trades in time order on a compounding account; ``stats`` reads them. ``shuffle``
is the permutation: every trade moved to a random minute of its own stock-day, inside the window.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import shorts_config as cfg

from constants_setups import SETUPS_EMA_PERIOD
from setup_scanner.bars import Bar
from setup_scanner.detector import candle_start
from setup_scanner.detectors import make_detector, trigger_up
from setup_scanner.scoring import ScoreTracker
from setup_scanner.series import ema

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class StockDay:
    ticker: str
    d: str                        # YYYY-MM-DD
    prior_close: float | None
    follow_from: float            # epoch seconds: the first minute the scanner followed it
    ssr_yesterday: bool | None
    bars: tuple[Bar, ...]


@dataclass
class Trade:
    ticker: str
    d: str
    kind: str | None
    ssr: str
    triggered_at: float
    entry: float
    stop: float
    target1: float
    risk: float
    half_px: float | None = None
    exit_px: float | None = None
    exit_reason: str | None = None
    gross_r: float | None = None
    shares: int = 0
    net_usd: float | None = None
    net_r: float | None = None
    skipped: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Costs:
    start_equity: float = cfg.START_EQUITY
    risk_pct: float = cfg.RISK_PCT
    max_position_pct: float = cfg.MAX_POSITION_PCT
    min_notional: float = cfg.MIN_NOTIONAL
    slippage: float = cfg.SLIPPAGE
    commission_per_share: float = cfg.COMMISSION_PER_SHARE
    commission_min: float = cfg.COMMISSION_MIN
    commission_max_pct: float = cfg.COMMISSION_MAX_PCT
    compound: bool = True


BASE = Costs()
DOUBLE = Costs(**cfg.COSTS_2X)


def _hm(text: str) -> int:
    h, m = str(text).split(":")
    return int(h) * 60 + int(m)


def et_minute(ts: float) -> int:
    when = datetime.fromtimestamp(ts, ET)
    return when.hour * 60 + when.minute


def _tracker(params: Any, *, entry: float, stop: float, target1: float, risk: float, ts: float, bar_t: float,
             half_on_entry_bar: bool = True) -> ScoreTracker:
    return ScoreTracker(entry=entry, stop=stop, target1=target1, risk=risk, triggered_at=ts, entry_bar_t=bar_t,
                        bailout_bars=params.bailout_bars, window_min=params.score_window_min, bar_sec=params.bar_sec,
                        half_on_entry_bar=half_on_entry_bar, side=params.side)


def untestable(params: Any) -> str | None:
    """Why this harness cannot test the rules, or None. It reads bars, never the tape: a flush exit (ADR 034) acts
    on flow readings it never has, so a result would pass on exits the template does not use (PR #789 review)."""
    mode = str(getattr(getattr(params, "flush", None), "mode", "off") or "off")
    if mode != "off":
        return (f"the template's flush exit is {mode!r}: this harness reads bars, never the tape, so it cannot test a "
                "flush exit -- put a template with flush_exit off in play to test it")
    return None


def _close(trade: Trade, tr: ScoreTracker) -> Trade:
    trade.half_px, trade.exit_px, trade.exit_reason = tr.half_px, tr.exit_px, tr.exit_reason
    trade.gross_r = tr.bar_r()
    return trade


def _stock_ok(params: Any, price: float, prior: float | None) -> bool:
    """The template's stock filter on what the files know (price, change); the rest by its 'unknown passes'."""
    stock = params.stock
    if not stock.active:
        return True
    change = (price / prior - 1.0) * 100.0 if prior else None
    return stock.check({"price": price, "change_pct": change}, None) is None


def walk(day: StockDay, params: Any) -> list[Trade]:
    """Every trade the lane's rules took on one stock-day (the template's own ``LaneParams``)."""
    bars = list(day.bars)
    start = next((i for i, b in enumerate(bars) if b.t >= day.follow_from), len(bars))
    if start >= len(bars):
        return []
    det = make_detector(params.setup, day.ticker, params.pattern)
    det.context = {"prior_close": day.prior_close, "ssr_yesterday": day.ssr_yesterday}
    up = trigger_up(params.setup)
    skip_ssr = getattr(params, "ssr", "trade") == "skip"
    kept_out: set[Any] = set()
    if start:
        det.on_bars(bars[:start])
    trades: list[Trade] = []
    on: tuple[ScoreTracker, Trade] | None = None
    for i in range(start, len(bars)):
        b = bars[i]
        for px, ts in ((b.o, b.t + 1.0), (b.h if up else b.lo, b.t + 30.0)):
            if on is not None:
                on[0].on_price(px, ts)
            for kind, view in det.on_price(px, ts, bar_open=b.o):
                if kind != "triggered":
                    continue
                setup = view.get("setup") or {}
                key = view.get("setup_key")
                if key in kept_out:
                    det.nth = max(0, det.nth - 1)      # a setup the template kept out is not one of its setups
                    continue
                if on is not None:
                    continue                            # one trade at a time on a stock
                trade = Trade(day.ticker, day.d, setup.get("kind"), det.ssr(), float(setup.get("triggered_at") or ts),
                              float(setup["entry"]), float(setup["stop"]), float(setup["target1"]), float(setup["risk"]))
                bar_t = float(setup.get("score_bar_t") or candle_start(params, trade.triggered_at))
                on = (_tracker(params, entry=trade.entry, stop=trade.stop, target1=trade.target1, risk=trade.risk,
                               ts=trade.triggered_at, bar_t=bar_t,
                               half_on_entry_bar=bool(setup.get("half_on_entry_bar", True))), trade)
        for kind, view in det.on_bars(bars[: i + 1]):
            if kind == "armed":
                ssr_now = det.ssr()
                if (skip_ssr and ssr_now != "off") or not _stock_ok(params, b.c, day.prior_close):
                    kept_out.add(view.get("setup_key"))
        if on is not None and on[0].on_bar(b, det.ema_now):
            trades.append(_close(on[1], on[0]))
            on = None
    if on is not None:                                  # the bars ran out before an exit: out at the last close
        on[0].exit_px = on[0].exit_px if on[0].exit_px is not None else bars[-1].c
        on[0].exit_reason = on[0].exit_reason or "close"
        trades.append(_close(on[1], on[0]))
    return trades


def run_day(job: tuple[list[StockDay], list[tuple[str, Any]]]) -> dict[str, list[Trade]]:
    """Every variant's trades on one day's stock-days (a worker process: importable, so it runs under spawn)."""
    days, rules = job
    out: dict[str, list[Trade]] = {name: [] for name, _ in rules}
    for sd in days:
        for name, params in rules:
            out[name].extend(walk(sd, params))
    return out


def commission(shares: int, value: float, c: Costs) -> float:
    if shares <= 0:
        return 0.0
    return min(max(shares * c.commission_per_share, c.commission_min), c.commission_max_pct * value)


def cost_trade(t: Trade, equity: float, c: Costs) -> Trade:
    """Size ``t`` on ``equity`` and cost it: a short sells at the entry less the slippage and covers each part at
    its price plus the slippage, IBKR's commission on every fill."""
    out = Trade(**{**t.__dict__, "extra": dict(t.extra)})
    if t.exit_px is None or t.risk <= 0:
        out.skipped = "not closed"
        return out
    shares = int(min(c.risk_pct * equity / t.risk, c.max_position_pct * equity / t.entry))
    if shares < 1 or shares * t.entry < c.min_notional:
        out.skipped = "too small to survive the commission"
        return out
    half = shares // 2 if t.half_px is not None else 0
    rest = shares - half
    gross = half * (t.entry - (t.half_px or 0.0)) + rest * (t.entry - t.exit_px)
    slip = c.slippage * 2 * shares
    fees = commission(shares, shares * t.entry, c) + commission(rest, rest * t.exit_px, c)
    if half:
        fees += commission(half, half * float(t.half_px), c)
    out.shares = shares
    out.net_usd = round(gross - slip - fees, 2)
    out.net_r = round(out.net_usd / (shares * t.risk), 4)
    return out


def account(trades: list[Trade], c: Costs = BASE) -> list[Trade]:
    """Every trade sized and costed in time order; equity moves at each day's end (``compound``)."""
    equity = c.start_equity
    out: list[Trade] = []
    by_day: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        by_day[t.d].append(t)
    for d in sorted(by_day):
        day_pnl = 0.0
        for t in sorted(by_day[d], key=lambda x: (x.triggered_at, x.ticker)):
            costed = cost_trade(t, equity, c)
            out.append(costed)
            day_pnl += costed.net_usd or 0.0
        if c.compound:
            equity += day_pnl
    return out


def stats(costed: list[Trade]) -> dict[str, Any]:
    taken = [t for t in costed if t.net_usd is not None]
    wins = sum(t.net_usd for t in taken if t.net_usd > 0)
    losses = -sum(t.net_usd for t in taken if t.net_usd < 0)
    years: dict[str, list[Trade]] = defaultdict(list)
    for t in taken:
        years[t.d[:4]].append(t)
    return {
        "trades": len(taken), "skipped": len(costed) - len(taken),
        "win_pct": round(100 * sum(1 for t in taken if t.net_usd > 0) / len(taken), 1) if taken else None,
        "pf": round(wins / losses, 3) if losses > 0 else None,         # JSON has no infinity: see no_losses
        "no_losses": bool(taken) and losses == 0 and wins > 0,
        "exp_r": round(sum(t.net_r for t in taken) / len(taken), 4) if taken else None,
        "net_usd": round(sum(t.net_usd for t in taken), 2),
        "by_year": {y: {"trades": len(ts), "net_usd": round(sum(t.net_usd for t in ts), 2),
                        "exp_r": round(sum(t.net_r for t in ts) / len(ts), 4)} for y, ts in sorted(years.items())},
    }


def best_year_removed(costed: list[Trade]) -> dict[str, Any]:
    s = stats(costed)
    if not s["by_year"]:
        return {"year": None, "exp_r": None, "ok": False}
    best = max(s["by_year"], key=lambda y: s["by_year"][y]["net_usd"])
    rest = [t for t in costed if t.net_usd is not None and t.d[:4] != best]
    exp = round(sum(t.net_r for t in rest) / len(rest), 4) if rest else None
    return {"year": best, "exp_r": exp, "ok": exp is not None and exp > 0}


def window_minutes(day: StockDay, params: Any) -> list[int]:
    """The bar indexes a shuffled entry may take: followed, inside the strategy's window, with a bar after it."""
    start, end = _hm(params.pattern.session_start), _hm(params.pattern.entry_cutoff)
    return [i for i, b in enumerate(day.bars[:-1])
            if b.t >= day.follow_from and start <= et_minute(b.t) < end]


def shuffled_trade(day: StockDay, params: Any, i: int, risk: float, closes_ema: list[float]) -> Trade:
    """A short at the open of bar ``i`` with the trade's own risk a share, out by the same rules."""
    bars = day.bars
    b = bars[i]
    entry = float(b.o)
    target_r = float(getattr(params.pattern, "target_r", 2.0))
    t = Trade(day.ticker, day.d, "shuffle", "off", b.t + 1.0, entry, entry + risk, entry - target_r * risk, risk)
    tr = _tracker(params, entry=entry, stop=t.stop, target1=t.target1, risk=risk, ts=t.triggered_at, bar_t=b.t)
    for j in range(i, len(bars)):
        if tr.on_bar(bars[j], closes_ema[j]):
            break
    if tr.exit_px is None:
        tr.exit_px, tr.exit_reason = bars[-1].c, "close"
    return _close(t, tr)


def shuffle(trades: list[Trade], days: dict[tuple[str, str], StockDay], params: Any, *, shuffles: int = cfg.SHUFFLES,
            seed: int = cfg.SHUFFLE_SEED, progress: Any = None) -> dict[str, Any]:
    """p = (1 + shuffles whose mean net R is at least the strategy's) / (shuffles + 1), each trade costed on a fixed
    account (no compounding) so a trade's R never depends on the shuffle before it."""
    fixed = Costs(compound=False)
    actual = [cost_trade(t, fixed.start_equity, fixed) for t in trades]
    actual = [t for t in actual if t.net_r is not None]
    if not actual:
        return {"p": None, "shuffles": 0, "actual_exp_r": None, "seed": seed, "ok": False}
    mean = sum(t.net_r for t in actual) / len(actual)
    rng = random.Random(seed)
    cache: dict[tuple[str, str], tuple[list[int], list[float]]] = {}
    at_least = 0
    for k in range(shuffles):
        total, n = 0.0, 0
        for t in actual:
            key = (t.ticker, t.d)
            if key not in cache:
                day = days[key]
                period = int(getattr(params.pattern, "ema_period", SETUPS_EMA_PERIOD))
                cache[key] = (window_minutes(day, params), ema([b.c for b in day.bars], period))
            allowed, closes_ema = cache[key]
            if not allowed:
                continue
            moved = cost_trade(shuffled_trade(days[key], params, rng.choice(allowed), t.risk, closes_ema),
                               fixed.start_equity, fixed)
            if moved.net_r is not None:
                total += moved.net_r
                n += 1
        if n and total / n >= mean:
            at_least += 1
        if progress is not None:
            progress(k + 1, shuffles)
    p = (1 + at_least) / (shuffles + 1)
    return {"p": round(p, 4), "shuffles": shuffles, "actual_exp_r": round(mean, 4), "seed": seed, "ok": p <= cfg.MAX_P}
