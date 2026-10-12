"""Time the front door's reads on real files, so "fast enough for agents" is a measured number."""
from __future__ import annotations

import time
from typing import Any

from market_reads import inventory, reads

from constants_sim import SIM_MASSIVE_QUOTES, SIM_MASSIVE_TRADES
from sim import massive_files, massive_index


def newest_indexed_day() -> str | None:
    """The newest day whose trades and quotes files both have a current index."""
    root = massive_files.root()
    for path in reversed(inventory.day_files(SIM_MASSIVE_QUOTES)):
        day = path.name[:10]
        trades_file = massive_files.day_file(SIM_MASSIVE_TRADES, day)
        if trades_file and massive_index.is_current(path, root) and massive_index.is_current(trades_file, root):
            return day
    return None


def _timed(name: str, call) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        out = call()
    except Exception as exc:  # noqa: BLE001 -- a bench line reports a failure, it never stops the bench
        return {"read": name, "seconds": round(time.monotonic() - t0, 2), "error": f"{type(exc).__name__}: {exc}"}
    rows = len(out["rows"]) if isinstance(out, dict) else len(out)
    extra = {"indexed": out.attrs.get("indexed")} if hasattr(out, "attrs") and "indexed" in out.attrs else {}
    return {"read": name, "seconds": round(time.monotonic() - t0, 2), "rows": rows, **extra}


def run(day: str | None = None, symbol: str = "TSLA") -> dict[str, Any]:
    """Each read once, on ``day`` (default: the newest fully indexed day)."""
    day = day or newest_indexed_day()
    if day is None:
        return {"error": "no day has both its trades and quotes indexed yet (tools/market_data.py index)"}
    return {"day": day, "symbol": symbol, "reads": [
        _timed(f"trades {symbol} whole day", lambda: reads.trades(symbol, day)),
        _timed(f"quotes {symbol} whole day", lambda: reads.quotes(symbol, day)),
        _timed(f"1-minute bars {symbol}", lambda: reads.bars(symbol, day, "1m")),
        _timed(f"10-second bars {symbol} 09:30-10:00", lambda: reads.bars(symbol, day, "10s", "09:30", "10:00")),
        _timed("movers: high +100%, price under $20, every year", lambda: reads.movers(high_min=100, price_max=20,
                                                                                      limit=200)),
        _timed(f"Gainers board {day} 09:45", lambda: reads.board(day, "09:45")),
    ]}
