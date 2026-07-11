"""
Tape/order-book feature math (Phase F). Pure functions only -- no I/O, no
orders. Operates on the same {bids, asks, l1_fallback} book shape used by
ibkr/depth.py and the /ws/ibkr/depth/{symbol} stream.

These are the numeric features Ross describes qualitatively in the course
(bid/ask imbalance, a seller stacked on the ask, spread width, buying
pressure drying up) turned into codeable numbers, per
Automation-Strategy-Backbone.md section 3: encode the *features*, but do not
let them drive the executor until enough labeled recordings exist to trust a
rule or a model.
"""
from __future__ import annotations

from constants import (
    L2_ASK_STACKED_RATIO,
    L2_BID_HEAVY_RATIO,
    L2_PRESSURE_DRYING_DROP_FRACTION,
    L2_PRESSURE_DRYING_LOOKBACK,
)


def _total_size(levels: list[dict]) -> float:
    return sum(level.get("size", 0) or 0 for level in levels)


def _best_price(levels: list[dict]) -> float | None:
    return levels[0]["price"] if levels else None


def bid_total(book: dict) -> float:
    return _total_size(book.get("bids", []))


def ask_total(book: dict) -> float:
    return _total_size(book.get("asks", []))


def best_bid(book: dict) -> float | None:
    return _best_price(book.get("bids", []))


def best_ask(book: dict) -> float | None:
    return _best_price(book.get("asks", []))


def spread(book: dict) -> float | None:
    bid, ask = best_bid(book), best_ask(book)
    if bid is None or ask is None:
        return None
    return round(ask - bid, 4)


def bid_ask_imbalance(book: dict) -> float | None:
    """(bid size - ask size) / (bid size + ask size), range -1..1.
    Positive = more resting buying interest than selling interest. None when
    both sides are empty (nothing to compare)."""
    bids, asks = bid_total(book), ask_total(book)
    total = bids + asks
    if total <= 0:
        return None
    return round((bids - asks) / total, 4)


def is_ask_stacked(book: dict) -> bool:
    """'Seller stacked on the ask' -- resting ask size dwarfs resting bid size."""
    bids, asks = bid_total(book), ask_total(book)
    if asks <= 0:
        return False
    if bids <= 0:
        return True
    return asks >= bids * L2_ASK_STACKED_RATIO


def is_bid_heavy(book: dict) -> bool:
    """Mirror of is_ask_stacked -- resting bid size dwarfs resting ask size."""
    bids, asks = bid_total(book), ask_total(book)
    if bids <= 0:
        return False
    if asks <= 0:
        return True
    return bids >= asks * L2_BID_HEAVY_RATIO


def compute_feature_dict(book: dict) -> dict:
    """Single-snapshot feature summary."""
    return {
        "bid_total": bid_total(book),
        "ask_total": ask_total(book),
        "imbalance": bid_ask_imbalance(book),
        "spread": spread(book),
        "ask_stacked": is_ask_stacked(book),
        "bid_heavy": is_bid_heavy(book),
    }


def is_buying_pressure_drying_up(window: list[dict]) -> bool:
    """True if resting bid size has dropped by at least
    L2_PRESSURE_DRYING_DROP_FRACTION from the start to the end of the window
    (oldest snapshot first). Needs at least 2 snapshots to compare."""
    if len(window) < 2:
        return False
    first_bid = bid_total(window[0])
    last_bid = bid_total(window[-1])
    if first_bid <= 0:
        return False
    return last_bid <= first_bid * (1 - L2_PRESSURE_DRYING_DROP_FRACTION)


def compute_feature_series(snapshots: list[dict]) -> list[dict]:
    """snapshots: oldest-first list of book dicts (or dicts with a "bids"/"asks"
    shape, e.g. rows from l2/store.py's get_snapshots()). Returns one feature
    dict per snapshot, each including a trailing-window `drying_up` flag."""
    series: list[dict] = []
    for i, book in enumerate(snapshots):
        features = compute_feature_dict(book)
        window_start = max(0, i - L2_PRESSURE_DRYING_LOOKBACK + 1)
        features["drying_up"] = is_buying_pressure_drying_up(snapshots[window_start:i + 1])
        series.append(features)
    return series
