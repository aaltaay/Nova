"""One stock's LULD bands, kept from its tape and its best bid / offer (pure; ADR 047).

maintainer: one-concern the Plan's reference-price state machine must live in one place

Feed it, in time order, every trade (``on_print``), the national best bid and offer
(``on_quote``), halts (``on_halt``) and tape gaps (``on_gap``); ``view(now)`` says where the
bands are. The rules are the LULD Plan's (Amendment 20, Sections V-VII; ``rules.py``):

- **The open.** The first reference is the listing exchange's opening print (a print with
  condition ``O`` from a venue that is not a trade-report facility) when it comes within
  five minutes of 09:30. For the next five minutes the pro-forma reference is the mean of
  every eligible trade since that print, the print included. If no opening print comes by
  09:35, the first reference is the mean of the eligible trades of 09:30-09:35.
- **After that** the pro-forma reference is the arithmetic mean of the eligible trades of the
  preceding five minutes, recomputed continuously. It becomes the reference when it is 1% or
  more away from the reference in force -- and only after that one has stood 30 seconds.
  Without an eligible trade in five minutes the reference stays.
- **A limit state** begins when the best offer rests on the lower band (or the best bid on
  the upper) without crossing; no new reference is made while it lasts. Fifteen seconds in it
  and the listing exchange pauses the stock. The Plan says the reference becomes the
  five-minute mean the moment a limit state ends (Section VI(B)(4)); the SIP's own band flags
  say it does not, so Nova keeps the reference in force (``Options``; measured by
  ``tools/luld_check.py``).
- **A pause or a halt** shows no band. The reopening print (condition ``5``) is the next
  reference, and the five minutes after it are read like the open's.

"Eligible" is Nova's own rule for a print that sets a price (``sale_conditions.py``): the
Plan's "eligible to update the last sale price".

**Exact or not.** The reference is a path: it depends on every eligible trade since the
open or the last reopen. A tracker that saw that (re)opening print and has heard every trade
since is ``exact`` -- the published rules, applied. One that started watching later can only
take the five-minute mean once it holds five minutes of tape and seed the reference with it;
the exchanges' reference is then within about 1% of Nova's, the band ``exact: false`` with
its likely spread. A lost stretch of tape (``on_gap``) makes an exact tracker approximate
until the next reopening. An approximate tracker never claims a limit state.

Times are epoch seconds on one clock: the host's arrival times live, the SIP's in a study.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from luld import rules
from luld.constants_luld import (
    LULD_AT_BAND_EPS,
    LULD_HISTORY_KEEP,
    LULD_LIMIT_STATE_SEC,
    LULD_MOVE_FRACTION,
    LULD_OPEN_CONDITION,
    LULD_OPEN_EARLY_SEC,
    LULD_OPEN_GRACE_SEC,
    LULD_PRICE_SCALE,
    LULD_REF_MIN_SEC,
    LULD_REOPEN_CONDITION,
    LULD_REPORT_VENUES,
    LULD_WARM_SEC,
    LULD_WINDOW_SEC,
)

_INF = math.inf
_MOVE = Fraction(str(LULD_MOVE_FRACTION))
_EPS = LULD_AT_BAND_EPS
# Float pre-checks of the 1% rule; the exact rational decides only between them.
_MOVE_LO = LULD_MOVE_FRACTION * (1 - 1e-6)
_MOVE_HI = LULD_MOVE_FRACTION * (1 + 1e-6)


@dataclass
class _Limit:
    side: str           # "down" (the offer on the lower band) | "up" (the bid on the upper)
    since: float
    band: float
    overdue: bool = False  # 15 s passed: the listing exchange should have paused it


@dataclass
class _Day:
    open_ts: float
    close_ts: float
    closing_ts: float


@dataclass(frozen=True)
class Options:
    """What the Plan leaves to the processors, measured instead of guessed (ADR 047).

    ``exit_updates_reference``: whether a limit state's end makes the five-minute mean the
    reference at once (Section VI(B)(4) reads so); ``exit_resets_clock``: whether that reference
    starts the 30 s floor again; ``reference_digits``: the decimals a mean is rounded to (half
    up) before it becomes the reference, None for none.

    The defaults are what matched the SIP's own band flags best (``luld/study.py``, the Massive
    flat files): no reference at a limit state's end, and the mean unrounded. GRML 2026-09-22
    10:49 shows why: after its bid sat 8 s on the 16.58 band, the SIP's next band (17.18 at
    10:50:15) kept the 30-second clock of the reference before the limit state, and a reference
    made at the limit state's end puts it at 17.22."""

    exit_updates_reference: bool = False
    exit_resets_clock: bool = False
    reference_digits: int | None = None
    # When the pro-forma reference is checked: "continuous" (every moment it can change -- a trade,
    # a trade leaving the window, the 30 s floor running out) or "trades" (each eligible trade only).
    reference_on: str = "continuous"


DEFAULT_OPTIONS = Options()


@dataclass
class Facts:
    """What the tracker cannot see on the tape: the day's previous close, the tier, coverage."""

    prev_close: float | None = None
    tier: int | None = None
    tier_basis: str | None = None
    # False when the tier is Nova's assumption (no index list; ``rules.tier_from_size``).
    tier_sure: bool = True
    covered: bool = True
    covered_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Tracker:
    def __init__(self, symbol: str, *, started_at: float, facts: Facts | None = None,
                 options: Options = DEFAULT_OPTIONS) -> None:
        self.symbol = (symbol or "").upper()
        self.facts = facts or Facts()
        self.options = options
        self._clock = started_at
        self._last_price: float | None = None
        self._last_print_ts: float | None = None
        self._bid: float | None = None
        self._ask: float | None = None
        self._quote_ts: float | None = None
        self._reset_day(started_at)

    # -- state per trading day -------------------------------------------------------------------
    def _reset_day(self, ts: float) -> None:
        bounds = rules.rth_bounds(ts)
        self._day = _Day(bounds[0], bounds[1], rules.closing_at(ts)) if bounds else None
        self._day_key = bounds[0] if bounds else None
        self._win: deque[tuple[float, int]] = deque()
        self._sum = 0
        # Premarket trades never count toward a reference.
        self._floor = (self._day.open_ts - LULD_OPEN_EARLY_SEC) if self._day else _INF
        self._ref: Fraction | None = None
        self._ref_f = 0.0
        self._ref_since: float | None = None
        self._ref_source: str | None = None
        self._exact = False
        self._anchor: dict[str, Any] | None = None
        self._open_seen = False
        self._reopen_ts = -_INF
        self._limit: _Limit | None = None
        self._halted_since: float | None = None
        self._await_reopen = False                # a halt ended; the next trade reopens
        self._tape_since = ts
        self._gap: dict[str, Any] | None = None   # the last tape gap that broke exactness
        self._history: deque[dict[str, Any]] = deque(maxlen=LULD_HISTORY_KEEP)
        self._straddle: str | None = None
        self._band_key: tuple | None = None
        self._band_val: tuple[float | None, float | None, rules.Parameter | None] = (None, None, None)

    def _roll_day(self, ts: float) -> None:
        bounds = rules.rth_bounds(ts)
        if (bounds[0] if bounds else None) != self._day_key:
            self._reset_day(ts)

    # -- inputs ----------------------------------------------------------------------------------
    def on_print(self, ts: float, price: float, *, eligible: bool, conditions: str | None = None,
                 exchange: str | None = None) -> None:
        if not (price and price > 0):
            return
        ts = self._advance(ts)
        day = self._day
        codes = set(conditions or "")
        report = (exchange or "").strip().upper() in LULD_REPORT_VENUES
        if day is not None and not report:
            if (LULD_REOPEN_CONDITION in codes and day.open_ts <= ts < day.close_ts
                    and ts >= self._reopen_ts + LULD_WINDOW_SEC):
                self._reopen(ts, price, "reopen")
            elif (LULD_OPEN_CONDITION in codes and not self._open_seen and self._halted_since is None
                  and day.open_ts - LULD_OPEN_EARLY_SEC <= ts <= day.open_ts + LULD_OPEN_GRACE_SEC):
                self._anchor_at(ts, price, "open")
        if eligible and self._await_reopen and day is not None and day.open_ts <= ts < day.close_ts:
            # A halt ended and trading resumed without a reopening print on Nova's tape.
            self._reopen(ts, price, "first_trade_after_halt", exact=False)
        if eligible and ts >= self._floor:
            self._win.append((ts, round(price * LULD_PRICE_SCALE)))
            self._sum += self._win[-1][1]
        self._last_price = price
        self._last_print_ts = ts
        if eligible or self.options.reference_on == "continuous":
            self._check_reference(ts)

    def on_quote(self, ts: float, bid: float | None, ask: float | None) -> None:
        ts = self._advance(ts)
        self._bid = bid if bid and bid > 0 else None
        self._ask = ask if ask and ask > 0 else None
        self._quote_ts = ts
        self._check_limit(ts)

    def on_halt(self, ts: float, halted: bool) -> None:
        ts = self._advance(ts)
        if halted and self._halted_since is None:
            self._halted_since = ts
            self._limit = None
            self._await_reopen = False
        elif not halted and self._halted_since is not None:
            self._halted_since = None
            self._await_reopen = True

    def on_gap(self, ts: float, reason: str) -> None:
        """Nova lost some of this stock's tape (a line ended, the feed went quiet): its five-minute
        mean is short of trades, so the reference is no longer exact."""
        ts = self._advance(ts)
        if self._ref is not None and self._exact:
            self._exact = False
            self._gap = {"ts": ts, "reason": reason}
        self._limit = None
        self._tape_since = ts

    def set_facts(self, facts: Facts) -> None:
        self.facts = facts

    def advance(self, ts: float) -> None:
        self._advance(ts)

    @property
    def clock(self) -> float:
        return self._clock

    @property
    def last_print_ts(self) -> float | None:
        return self._last_print_ts

    # -- the clock -------------------------------------------------------------------------------
    def _advance(self, t: float) -> float:
        """Run the continuous rules to ``t``: window evictions, the 30 s floor, 15 s in a limit
        state, the open's deadline, the closing doubling and the close. Returns ``t`` (never
        before the clock)."""
        if t < self._clock:
            t = self._clock
        self._roll_day(t)
        while True:
            nxt = self._next_moment()
            if nxt > t:
                break
            self._clock = nxt
            self._evict(nxt)
            self._on_moment(nxt)
        self._clock = t
        self._evict(t)
        return t

    def _next_moment(self) -> float:
        nxt = self._win[0][0] + LULD_WINDOW_SEC if self._win else _INF
        if self._ref is not None and self._ref_since is not None and self._limit is None:
            unlock = self._ref_since + LULD_REF_MIN_SEC
            if unlock > self._clock:
                nxt = min(nxt, unlock)
        if self._limit is not None and not self._limit.overdue:
            nxt = min(nxt, self._limit.since + LULD_LIMIT_STATE_SEC)
        day = self._day
        if day is not None:
            for edge in (day.open_ts + LULD_OPEN_GRACE_SEC, day.closing_ts, day.close_ts):
                if edge > self._clock:
                    nxt = min(nxt, edge)
            if self._ref is None and self._anchor is None:
                warm = self._tape_since + LULD_WARM_SEC
                if warm > self._clock:
                    nxt = min(nxt, warm)
        return nxt

    def _evict(self, t: float) -> None:
        cut = t - LULD_WINDOW_SEC
        win = self._win
        while win and win[0][0] <= cut:
            self._sum -= win.popleft()[1]

    def _on_moment(self, t: float) -> None:
        day = self._day
        if day is None:
            return
        if t >= day.close_ts:
            self._ref, self._limit, self._straddle = None, None, None
            return
        if self._limit is not None and t >= self._limit.since + LULD_LIMIT_STATE_SEC:
            self._limit.overdue = True
        if self.options.reference_on == "continuous" or self._ref is None:
            self._check_reference(t)
        self._check_limit(t)

    # -- the rules ---------------------------------------------------------------------------------
    def _set_floor(self, ts: float) -> None:
        self._floor = ts
        while self._win and self._win[0][0] < ts:
            self._sum -= self._win.popleft()[1]

    def _anchor_at(self, ts: float, price: float, kind: str, *, exact: bool = True) -> None:
        self._set_floor(ts)
        self._anchor = {"kind": kind, "ts": ts, "price": price}
        self._open_seen = True
        self._limit = None
        if exact:
            self._gap = None
        self._set_ref(Fraction(str(price)), ts, kind, exact=exact)

    def _reopen(self, ts: float, price: float, kind: str, *, exact: bool = True) -> None:
        self._halted_since = None
        self._await_reopen = False
        self._reopen_ts = ts
        self._anchor_at(ts, price, kind, exact=exact)

    def _set_ref(self, value: Fraction | None, ts: float, source: str, *, exact: bool | None = None) -> None:
        if value is None:
            return
        self._ref, self._ref_f, self._ref_since, self._ref_source = value, float(value), ts, source
        if exact is not None:
            self._exact = exact
        self._history.append({"ts": round(ts, 3), "reference": round(float(value), 4), "source": source})

    def _mean(self) -> Fraction | None:
        """The pro-forma reference: the window's mean, rounded as the options say."""
        if not self._win:
            return None
        mean = Fraction(self._sum, len(self._win) * LULD_PRICE_SCALE)
        digits = self.options.reference_digits
        return mean if digits is None else rules.round_to(mean, digits)

    def _first_reference(self, t: float) -> None:
        """No reference yet and no (re)opening print: the Plan's fallback at 09:35, or Nova's seed."""
        day = self._day
        if self._ref is not None or self._anchor is not None or day is None:
            return
        if not (day.open_ts + LULD_OPEN_GRACE_SEC <= t < day.close_ts):
            return
        if self._tape_since <= day.open_ts:
            # Nova watched through the open and saw no opening print: the 09:30-09:35 mean
            # (Section V(B)(2)). Approximate: the print may have come in a form Nova misread.
            self._set_ref(self._mean(), t, "open_mean", exact=False)
        elif t >= self._tape_since + LULD_WARM_SEC:
            self._set_ref(self._mean(), t, "seeded", exact=False)

    def _check_reference(self, t: float) -> None:
        """The continuous pro-forma rule: 1% away and the old reference 30 s old."""
        if self._ref is None:
            self._first_reference(t)
            return
        if self._limit is not None or self._halted_since is not None:
            return
        day = self._day
        if day is None or not (day.open_ts <= t < day.close_ts):
            return
        if self._ref_since is not None and t < self._ref_since + LULD_REF_MIN_SEC - 1e-9:
            return
        n = len(self._win)
        if not n:
            return
        pf_f = self._sum / (n * LULD_PRICE_SCALE)
        digits = self.options.reference_digits
        if digits is not None:
            pf_f = math.floor(pf_f * 10 ** digits + 0.5) / 10 ** digits
        move = abs(pf_f - self._ref_f)
        if move < self._ref_f * _MOVE_LO:
            return
        pf = self._mean()
        if move > self._ref_f * _MOVE_HI or abs(pf - self._ref) >= self._ref * _MOVE:
            self._set_ref(pf, t, "mean")

    def _bands_now(self, t: float) -> tuple[float | None, float | None, rules.Parameter | None]:
        day = self._day
        if self._ref is None or day is None:
            return None, None, None
        closing = t >= day.closing_ts
        key = (self._ref, self.facts.prev_close, self.facts.tier, closing)
        if key != self._band_key:
            param = rules.parameter(self.facts.prev_close, self.facts.tier, closing=closing)
            if param is None:
                self._band_val = (None, None, None)
            else:
                lo, up = rules.bands(self._ref, param)
                self._band_val = (float(lo) if lo is not None else None, float(up), param)
            self._band_key = key
        return self._band_val

    def _check_limit(self, t: float) -> None:
        day = self._day
        if (day is None or not (day.open_ts <= t < day.close_ts) or self._halted_since is not None
                or self._ref is None or not self._exact or not self.facts.covered):
            self._limit, self._straddle = None, None
            return
        lo, up, _param = self._bands_now(t)
        if up is None:
            self._limit, self._straddle = None, None
            return
        bid, ask = self._bid, self._ask
        crossed = bid is not None and ask is not None and bid > ask + 1e-9
        at_lo = lo is not None and ask is not None and ask <= lo + _EPS and not crossed
        at_up = bid is not None and bid >= up - _EPS and not crossed
        lim = self._limit
        if lim is None:
            if at_lo or at_up:
                side = "down" if at_lo else "up"
                self._limit = _Limit(side, t, (lo if side == "down" else up) or 0.0)
        elif not (at_lo if lim.side == "down" else at_up):
            # Out of the limit state: the five-minute mean, at once (Section VI(B)(4)).
            self._limit = None
            if self.options.exit_updates_reference:
                since = self._ref_since
                self._set_ref(self._mean() or self._ref, t, "limit_exit")
                if not self.options.exit_resets_clock:
                    self._ref_since = since
            elif self.options.reference_on == "continuous":
                self._check_reference(t)   # the continuous rule, held during the limit state, applies again
            lo, up, _param = self._bands_now(t)
        self._straddle = None
        if self._limit is None and lo is not None and up is not None and bid is not None and ask is not None \
                and not crossed:
            if bid < lo - _EPS and lo <= ask <= up:
                self._straddle = "down"
            elif ask > up + _EPS and lo <= bid <= up:
                self._straddle = "up"

    # -- the answer --------------------------------------------------------------------------------
    def view(self, now: float) -> dict[str, Any]:
        """Where the bands are at ``now`` (``views.tracker_view`` turns this into the wire shape)."""
        self._advance(now)
        day = self._day
        lo, up, param = self._bands_now(self._clock)
        warm_until = None
        if self._ref is None and self._anchor is None and day is not None:
            warm_until = max(self._tape_since + LULD_WARM_SEC, day.open_ts + LULD_OPEN_GRACE_SEC)
        spread = None
        if self._ref is not None and not self._exact and param is not None:
            spread = _approx_spread(self._ref, param)
        lim = self._limit
        return {
            "day_open": day.open_ts if day else None,
            "day_close": day.close_ts if day else None,
            "closing_at": day.closing_ts if day else None,
            "in_rth": bool(day and day.open_ts <= self._clock < day.close_ts),
            "reference": round(float(self._ref), 4) if self._ref is not None else None,
            "reference_since": self._ref_since,
            "reference_source": self._ref_source,
            "exact": self._exact,
            "lower": lo,
            "upper": up,
            "parameter": param,
            "spread": spread,
            "anchor": dict(self._anchor) if self._anchor else None,
            "limit": ({"side": lim.side, "since": lim.since, "band": lim.band, "overdue": lim.overdue,
                       "pause_at": lim.since + LULD_LIMIT_STATE_SEC} if lim else None),
            "straddle": self._straddle,
            "halted_since": self._halted_since,
            "await_reopen": self._await_reopen,
            "tape_since": self._tape_since,
            "warm_until": warm_until,
            "gap": dict(self._gap) if self._gap else None,
            "last": self._last_price,
            "last_ts": self._last_print_ts,
            "bid": self._bid,
            "ask": self._ask,
            "window_trades": len(self._win),
            "history": list(self._history),
            "clock": self._clock,
        }


def _approx_spread(ref: Fraction, param: rules.Parameter) -> float:
    """How far an approximate band may sit from the exchanges': the band of a reference 1% away."""
    _lo, up = rules.bands(ref, param)
    _lo2, up2 = rules.bands(ref * (1 + _MOVE), param)
    return round(float(up2 - up), 2)
