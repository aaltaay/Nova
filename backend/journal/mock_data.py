"""
Synthetic journal trades for exercising the Journal UI and go/no-go math
before Phase D (paper execution) exists and can populate the trades table
for real.

Every row this module inserts is tagged `is_mock=1` (see journal/db.py) so it
is excluded from real metrics by default (`include_mock=False`, the default
on every store/metrics function) and is only ever visible in the UI when a
user explicitly flips the "Show demo data" toggle in the Journal panel.

The 12 trades below are a fixed, hand-written dataset (not randomly
generated) so a reviewer can read every row and know exactly what is being
tested: a ~58% win rate, a ~2.6:1 profit/loss ratio (clears the 2:1 target),
and one intentionally non-adherent trade so the adherence criterion fails --
this exercises the pass/fail/pending states of all three go/no-go criteria
in one seed instead of only the all-empty state.

Run directly to seed or clear:
    py -3 -m journal.mock_data seed
    py -3 -m journal.mock_data clear
"""
from __future__ import annotations

import sys
import time

from journal.db import init_db
from journal.store import clear_mock_trades, record_trade

# (symbol, setup, side, qty, entry, stop, target, exit, pnl, adherent, days_ago_closed, hold_minutes, notes)
# days_ago spreads rows across the calendar so Reports year/month views light up
# multiple win/loss days; P&L totals stay identical to the original same-day seed.
_MOCK_TRADES: list[tuple] = [
    ("AARD", "gap_and_go", "long", 200, 4.10, 3.90, 4.50, 4.50, 80.0, True, 0, 6, "Clean break of premarket high, held the 9 EMA on the pullback."),
    ("JZXN", "bull_flag", "long", 100, 6.05, 5.90, 6.35, 5.90, -15.0, True, 1, 3, "Stopped out on the flag breakdown, exited at the plan's stop."),
    ("YSXT", "abcd", "long", 300, 1.30, 1.20, 1.50, 1.50, 60.0, True, 2, 9, "Textbook ABCD, point D broke B cleanly."),
    ("NVVE", "gap_and_go", "long", 150, 2.55, 2.35, 2.95, 2.35, -30.0, False, 3, 4, "Non-adherent: added size after entry instead of sizing at signal time."),
    ("SUNE", "bull_flag", "long", 100, 3.20, 3.00, 3.60, 3.60, 40.0, True, 5, 7, "Flagpole held, entered on break of flag high."),
    ("QTTB", "gap_and_go", "short", 100, 15.80, 16.00, 15.20, 15.20, 60.0, True, 7, 5, "Faded the gap after premarket high rejected twice."),
    ("FGI", "abcd", "long", 200, 5.40, 5.20, 5.80, 5.20, -40.0, True, 10, 4, "C held below the 9 EMA longer than expected, stopped at plan stop."),
    ("MIMI", "gap_and_go", "long", 250, 2.20, 2.05, 2.50, 2.50, 75.0, True, 14, 6, "Second gap-and-go attempt of the day, cleared prior high."),
    ("WNW", "bull_flag", "short", 100, 8.10, 8.30, 7.70, 7.70, 40.0, True, 18, 5, "Bear flag mirror of the long setup, same 9 EMA rule."),
    ("YMAT", "abcd", "long", 150, 3.75, 3.55, 4.15, 3.55, -30.0, True, 21, 3, "A-B move faded before D triggered, stopped out at plan stop."),
    ("KXIN", "gap_and_go", "long", 100, 4.90, 4.70, 5.30, 5.30, 40.0, True, 28, 8, "Held premarket high on the retest, ran to target."),
    ("SNAL", "abcd", "long", 200, 2.10, 1.90, 2.50, 2.10, -12.0, True, 35, 2, "Chopped around point C, exited flat-ish for a small loss on a tight stop."),
]


def generate_mock_trades() -> list[dict]:
    """Returns the fixed dataset as plain dicts with absolute timestamps
    computed from "now" -- read-only, does not touch the database."""
    now = time.time()
    rows = []
    for (symbol, setup, side, qty, entry, stop, target, exit_price, pnl,
         adherent, days_ago_closed, hold_minutes, notes) in _MOCK_TRADES:
        closed_ts = now - days_ago_closed * 86400 - 4 * 3600  # afternoon ET-ish
        opened_ts = closed_ts - hold_minutes * 60
        rows.append({
            "symbol": symbol, "setup": setup, "side": side, "qty": qty,
            "entry_price": entry, "stop_price": stop, "target_price": target,
            "exit_price": exit_price, "pnl": pnl, "adherent": adherent,
            "opened_ts": opened_ts, "closed_ts": closed_ts, "notes": notes,
        })
    return rows


def seed_mock_trades() -> int:
    """Clears any existing mock trades then inserts the fixed dataset fresh.
    Safe to re-run. Returns the number of rows inserted."""
    init_db()
    clear_mock_trades()
    for row in generate_mock_trades():
        record_trade(
            symbol=row["symbol"], setup=row["setup"], side=row["side"], qty=row["qty"],
            entry_price=row["entry_price"], stop_price=row["stop_price"],
            target_price=row["target_price"], exit_price=row["exit_price"],
            pnl=row["pnl"], adherent=row["adherent"], opened_ts=row["opened_ts"],
            closed_ts=row["closed_ts"], notes=row["notes"], is_mock=True,
        )
    return len(_MOCK_TRADES)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if action == "seed":
        n = seed_mock_trades()
        print(f"Seeded {n} mock trades (is_mock=1).")
    elif action == "clear":
        init_db()
        n = clear_mock_trades()
        print(f"Cleared {n} mock trades.")
    else:
        print("Usage: py -3 -m journal.mock_data [seed|clear]")
        sys.exit(1)
