"""The day read (ADR 053): six stated checks and a Bullish / Mixed / Bearish verdict -- rules, not a model.

Each check is green, amber (neither), red, waiting (its data cannot exist yet, with when it starts) or unknown
(its source has not answered, with why). The verdict counts only green and red: bullish when green - red reaches
``MARKET_DAY_READ_BULLISH_NET``, bearish when red - green reaches ``MARKET_DAY_READ_BEARISH_NET``, else mixed;
no verdict under ``MARKET_DAY_READ_MIN_KNOWN`` checks with data. Pure over the inputs given.
"""
from __future__ import annotations

from typing import Any

from constants_market_board import (
    MARKET_DAY_READ_BEARISH_NET,
    MARKET_DAY_READ_BREADTH_RATIO,
    MARKET_DAY_READ_BULLISH_NET,
    MARKET_DAY_READ_FUTURES_GREEN,
    MARKET_DAY_READ_GAPPERS_GREEN_PCT,
    MARKET_DAY_READ_GAPPERS_MIN,
    MARKET_DAY_READ_GAPPERS_RED_PCT,
    MARKET_DAY_READ_MIN_KNOWN,
    MARKET_DAY_READ_RUNNERS_X,
    MARKET_DAY_READ_SMALL_CAPS_PT,
    MARKET_DAY_READ_VIX_PCT,
    MARKET_INDEX_FUTURES,
)


def _check(cid: str, label: str, state: str, value: float | None, text: str, *, starts_at: float | None = None,
           why: str | None = None) -> dict[str, Any]:
    return {"id": cid, "label": label, "state": state, "value": value, "text": text, "starts_at": starts_at,
            "why": why}


def futures(quotes: dict[str, dict]) -> dict[str, Any]:
    label = "Futures up across the board"
    moves = [(quotes.get(i) or {}).get("change_pct") for i in MARKET_INDEX_FUTURES]
    if any(m is None for m in moves):
        return _check("futures", label, "unknown", None, "--", why="IBKR has not quoted all four index futures")
    up = sum(1 for m in moves if m > 0)
    down = sum(1 for m in moves if m < 0)
    state = "green" if up >= MARKET_DAY_READ_FUTURES_GREEN else "red" if down >= MARKET_DAY_READ_FUTURES_GREEN else "amber"
    return _check("futures", "Futures up across the board" if state != "red" else "Futures down across the board",
                  state, float(up), f"{up} of {len(moves)} up")


def breadth(block: dict[str, Any], open_at: float) -> dict[str, Any]:
    label = "Breadth: advancers vs decliners"
    if block.get("state") == "waiting":
        return _check("breadth", label, "waiting", None, "starts 09:30", starts_at=open_at)
    adv, dec = block.get("advancing"), block.get("declining")
    if block.get("state") != "ok" or adv is None or not dec:
        return _check("breadth", label, "unknown", None, "--", why=block.get("why") or "no NYSE breadth yet")
    ratio = adv / dec
    state = ("green" if ratio >= MARKET_DAY_READ_BREADTH_RATIO
             else "red" if ratio <= 1.0 / MARKET_DAY_READ_BREADTH_RATIO else "amber")
    text = f"{ratio:.1f} : 1" if ratio >= 1 else f"1 : {1.0 / ratio:.1f}"
    return _check("breadth", label, state, round(ratio, 2), text)


def vix(quote: dict | None) -> dict[str, Any]:
    label = "Fear gauge (VIX)"
    pct = (quote or {}).get("change_pct")
    if pct is None:
        return _check("vix", label, "unknown", None, "--", why=(quote or {}).get("error") or "IBKR has not quoted VIX")
    state = "green" if pct <= -MARKET_DAY_READ_VIX_PCT else "red" if pct >= MARKET_DAY_READ_VIX_PCT else "amber"
    word = "falling" if pct < 0 else "rising" if pct > 0 else "flat"
    return _check("vix", f"Fear gauge {word} (VIX)", state, pct, f"{(quote or {}).get('last'):.2f}")


def small_caps(spread_pt: float | None) -> dict[str, Any]:
    label = "Small caps vs large caps"
    if spread_pt is None:
        return _check("small_caps", label, "unknown", None, "--", why="needs both RTY and ES")
    state = ("green" if spread_pt >= MARKET_DAY_READ_SMALL_CAPS_PT
             else "red" if spread_pt <= -MARKET_DAY_READ_SMALL_CAPS_PT else "amber")
    words = "Small caps beating large caps" if spread_pt > 0 else "Small caps lagging large caps"
    return _check("small_caps", words, state, spread_pt, f"{spread_pt:+.2f} pt")


def runners(today: int | None, average: float | None) -> dict[str, Any]:
    label = "Small-cap runners vs normal"
    if today is None or not average:
        return _check("runners", label, "unknown", None, "--",
                      why="Nova has too few recorded sessions to compare" if today is not None else
                      "Nova's scanner history has not been read")
    x = today / average
    state = "green" if x >= MARKET_DAY_READ_RUNNERS_X else "red" if x <= 1.0 / MARKET_DAY_READ_RUNNERS_X else "amber"
    words = "Small-cap runners above normal" if x >= 1 else "Small-cap runners below normal"
    return _check("runners", words, state, float(today), f"{today} vs {average:.0f} avg")


def gappers(held: int, total: int, opened: bool, open_at: float) -> dict[str, Any]:
    label = "Gappers holding their open"
    if not opened:
        return _check("gappers", label, "waiting", None, "starts 09:30", starts_at=open_at)
    if total < MARKET_DAY_READ_GAPPERS_MIN:
        return _check("gappers", label, "unknown", None, f"{held} of {total}",
                      why=f"fewer than {MARKET_DAY_READ_GAPPERS_MIN} 20%+ gappers seen on the board")
    rate = 100.0 * held / total
    state = ("green" if rate >= MARKET_DAY_READ_GAPPERS_GREEN_PCT
             else "red" if rate <= MARKET_DAY_READ_GAPPERS_RED_PCT else "amber")
    return _check("gappers", label, state, round(rate, 1), f"{held} of {total}")


def verdict(checks: list[dict[str, Any]]) -> dict[str, Any]:
    green = sum(1 for c in checks if c["state"] == "green")
    red = sum(1 for c in checks if c["state"] == "red")
    known = sum(1 for c in checks if c["state"] in ("green", "amber", "red"))
    if known < MARKET_DAY_READ_MIN_KNOWN:
        word = None
    elif green - red >= MARKET_DAY_READ_BULLISH_NET:
        word = "bullish"
    elif red - green >= MARKET_DAY_READ_BEARISH_NET:
        word = "bearish"
    else:
        word = "mixed"
    return {"verdict": word, "green": green, "red": red, "known": known, "total": len(checks), "checks": checks}
