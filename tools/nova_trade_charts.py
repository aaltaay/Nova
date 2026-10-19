"""Trade list in, marked charts out: 1..9 stock-days of fills drawn on sub-minute bars by Nova's native renderer.

Usage: py -3 tools/nova_trade_charts.py export --trades-file trades.json --output NEWDIR
  --massive-root E:\\Nova\\massive --gateway-root <NOVA_CHECKOUT> [--bar-seconds 10] [--before 300] [--after 120]

Each trade is {symbol, date, entry_time "HH:MM:SS[.f]" ET, entry_price, exit_time, exit_price} (or ``exits``: a list
of {time, price} for partial exits) with optional ``stop`` / ``pivot`` lines and a ``label``. Trades on one stock-day
share one chart. Bars come from the window's minutes of that day's Massive trades through the market data front door
(``market_reads.bars``, the Sim's sub-minute rule); fills are caller marks, never inferred. SOP: architecture/schema/local-historical-charts.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import nova_trade_bar_cache as bar_cache
from nova_historical_charts import checked_gateway, run_native_export
from nova_historical_resolver import (
    HistoricalChartError,
    _valid_label,
    _write_json,
    file_sha256,
    local_path,
    validate_request,
)

REPO = Path(__file__).resolve().parents[1]
BAR_SECONDS = (1, 5, 10, 15, 30)
MAX_STOCK_DAYS = 9
MAX_EXITS = 8
TRADE_KEYS = {"symbol", "date", "entry_time", "entry_price", "exit_time", "exit_price", "exits", "stop", "pivot",
              "label"}
CLOCK = re.compile(r"(\d{2}):(\d{2}):(\d{2})(\.\d{1,6})?\Z")
MASSIVE_ROOT_ENV = "NOVA_MARKET_DATA_DIR"
TRADES_DATASET = "trades_v1"
READ_THREADS = 9


def _bad(message: str) -> HistoricalChartError:
    return HistoricalChartError("invalid_trade", message)


def _second(value: Any) -> float:
    match = CLOCK.fullmatch(value) if isinstance(value, str) else None
    if not match or int(match[1]) > 23 or int(match[2]) > 59 or int(match[3]) > 59:
        raise _bad("Times are ET HH:MM:SS with optional fractional seconds")
    return int(match[1]) * 3600 + int(match[2]) * 60 + int(match[3]) + float(match[4] or 0)


def _price(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise _bad("Prices must be finite and positive")
    return float(value)


def _clock(second: float) -> str:
    whole = int(second)
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}"


def _fills(trade: dict[str, Any]) -> tuple[tuple[float, float], list[tuple[float, float]]]:
    entry = (_second(trade.get("entry_time")), _price(trade.get("entry_price")))
    if "exits" in trade:
        if "exit_time" in trade or "exit_price" in trade:
            raise _bad("Give exit_time / exit_price or exits, not both")
        raw = trade["exits"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_EXITS or any(
                not isinstance(leg, dict) or leg.keys() != {"time", "price"} for leg in raw):
            raise _bad(f"exits is a list of 1..{MAX_EXITS} {{time, price}} objects")
        exits = [(_second(leg["time"]), _price(leg["price"])) for leg in raw]
    else:
        exits = [(_second(trade.get("exit_time")), _price(trade.get("exit_price")))]
    if any(second < entry[0] for second, _ in exits):
        raise _bad("An exit cannot come before its entry")
    return entry, exits


def _marks(trade: dict[str, Any], entry: tuple[float, float], exits: list[tuple[float, float]]) -> list[dict]:
    tag = trade.get("label")
    if tag is not None and not _valid_label(tag, 40):
        raise _bad("label is 1..40 printable characters")
    buy = f"Buy {entry[1]:.2f}" + (f" ({tag})" if tag else "")
    marks = [dict(kind="trade_marker", side="buy", second=entry[0], price=entry[1], label=buy, color="green")]
    marks += [dict(kind="trade_marker", side="sell", second=second, price=price, label=f"Sell {price:.2f}",
                   color="red") for second, price in exits]
    for key, color in (("stop", "grey"), ("pivot", "gold")):
        if trade.get(key) is not None:
            level = _price(trade[key])
            marks.append(dict(kind="horizontal_line", price=level, label=f"{key.title()} {level:.2f}", color=color))
    return marks


def normalize_trades(trades: Any, *, bar_seconds: int = 10, before_s: int = 300,
                     after_s: int = 120) -> list[dict[str, Any]]:
    """One plan per stock-day: the window around its fills on the bar grid, and every fill and level as a mark."""
    if isinstance(bar_seconds, bool) or bar_seconds not in BAR_SECONDS:
        raise HistoricalChartError("invalid_bar_seconds", f"Bars are {', '.join(map(str, BAR_SECONDS))} seconds")
    for span in (before_s, after_s):
        if isinstance(span, bool) or not isinstance(span, int) or not 0 <= span <= 4 * 3600:
            raise _bad("before / after are whole seconds from 0 through 14400")
    if not isinstance(trades, list) or not trades:
        raise HistoricalChartError("invalid_entries", "Give a non-empty list of trades")
    days: dict[tuple[str, str], dict[str, Any]] = {}
    for trade in trades:
        if not isinstance(trade, dict) or trade.keys() - TRADE_KEYS:
            raise _bad("Unknown trade fields; see the module docstring")
        symbol, day = trade.get("symbol"), trade.get("date")
        validate_request(symbol, day)
        entry, exits = _fills(trade)
        plan = days.setdefault((day, symbol), dict(symbol=symbol, day=day, first=entry[0], last=entry[0],
                                                    annotations=[]))
        plan["first"] = min(plan["first"], entry[0])
        plan["last"] = max(plan["last"], *(second for second, _ in exits))
        plan["annotations"] += _marks(trade, entry, exits)
    if len(days) > MAX_STOCK_DAYS:
        raise HistoricalChartError("invalid_entries", f"At most {MAX_STOCK_DAYS} stock-days per gallery")
    plans = []
    for _, plan in sorted(days.items()):
        if len(plan["annotations"]) > 32:
            raise _bad("At most 32 marks per stock-day")
        start = max(0, int(plan.pop("first") - before_s) // bar_seconds * bar_seconds)
        end = min(86400, math.ceil((plan.pop("last") + after_s) / bar_seconds) * bar_seconds)
        plans.append(dict(plan, start_s=start, end_s=max(end, start + bar_seconds)))
    return plans


def project_bars(frame: Any, start_s: int, end_s: int, bar_seconds: int) -> tuple[list[dict], int]:
    """``market_reads.bars`` rows in the window; a bucket with volume but no price-setting print stays a gap."""
    return project_rows(bar_cache.rows_from_frame(frame), start_s, end_s, bar_seconds)


def project_rows(rows: bar_cache.Rows, start_s: int, end_s: int, bar_seconds: int) -> tuple[list[dict], int]:
    bars, dropped = [], 0
    for second, *prices, volume in rows:
        if not start_s <= second < end_s or second % bar_seconds:
            continue
        if not all(p is not None and math.isfinite(p) and p > 0 for p in prices):
            dropped += 1
            continue
        o, h, low, c = prices
        bars.append(dict(s=int(second), o=o, h=h, l=low, c=c, v=float(volume)))
    return bars, dropped


def _front_door_read(massive_root: Path) -> Callable:
    os.environ[MASSIVE_ROOT_ENV] = str(massive_root)
    sys.path.insert(0, str(REPO / "research"))
    from market_reads import reads
    return reads.bars


def _source(massive_root: Path, day: str) -> Path:
    path = massive_root / TRADES_DATASET / day[:4] / day[5:7] / f"{day}.csv.gz"
    if not path.is_file():
        raise HistoricalChartError("day_missing", f"No {TRADES_DATASET} file for {day} under the Massive root")
    return path


def _read_span(plan: dict[str, Any]) -> tuple[str, str | None, tuple[int, int]]:
    """The whole minutes around the chart's window: ``start`` / ``end`` for the reader and the span in seconds."""
    first, last = plan["start_s"] // 60 * 60, math.ceil(plan["end_s"] / 60) * 60
    return _clock(first), None if last >= 86400 else _clock(last), (first, min(last, 86400))


def _project(plan: dict[str, Any], bar_seconds: int, massive_root: Path, read: Callable | None,
             cache_root: Path | None) -> tuple[list, dict]:
    """Either reader is asked for the window's whole minutes only (``market_reads`` parses only those lines). A
    caller's ``read`` is never cached; the front door's bars are, so a later chart inside that span is a hit."""
    symbol, day, tf = plan["symbol"], plan["day"], f"{bar_seconds}s"
    start, end, span = _read_span(plan)
    if read is not None:
        source = before = None
        rows, cache = bar_cache.rows_from_frame(read(symbol, day, tf, start, end)), "off"
    else:
        source = _source(massive_root, day)
        before = source.stat()
        rows, cache = bar_cache.day_rows(cache_root, source, symbol, day, bar_seconds, span,
                                         lambda: _front_door_read(massive_root)(symbol, day, tf, start, end))
    bars, dropped = project_rows(rows, plan["start_s"], plan["end_s"], bar_seconds)
    if not bars:
        raise HistoricalChartError("symbol_missing", f"{plan['symbol']} has no priced trades in its window")
    info = dict(dataset=TRADES_DATASET, exact_ticker=plan["symbol"], reader="market_reads.bars",
                rule="price-setting prints set OHLC; every trade counts in volume (ADR 046)",
                price_adjustment="none_same_session", window_s=[plan["start_s"], plan["end_s"]],
                read_span_s=list(span), volume_only_buckets_left_as_gaps=dropped, cache=cache)
    if source:
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise HistoricalChartError("input_changed", "The trades file changed during the read")
        info.update(path=str(source), size=after.st_size, mtime_ns=after.st_mtime_ns)
    return bars, info


def resolve_trade_bundle(trades: Any, output: Path, massive_root: Path, *, bar_seconds: int = 10,
                         before_s: int = 300, after_s: int = 120, family: str | None = None,
                         read: Callable | None = None, cache_root: Path | None = None) -> dict[str, Any]:
    """Read every stock-day (in parallel) before claiming ``output``; then freeze the bundle the exporter checks."""
    began = time.perf_counter()
    plans = normalize_trades(trades, bar_seconds=bar_seconds, before_s=before_s, after_s=after_s)
    family = family or f"Trades on {bar_seconds}-second bars"
    if not _valid_label(family, 80):
        raise HistoricalChartError("invalid_family", "Family label must be 1..80 printable characters")
    root = local_path(massive_root)
    if not (root / TRADES_DATASET).is_dir():
        raise HistoricalChartError("trades_root_missing", f"The Massive root has no {TRADES_DATASET} folder")
    target = local_path(output, must_exist=False)
    if not local_path(target.parent).is_dir() or target.exists():
        raise HistoricalChartError("output_exists", "Use a new output directory with an existing local parent")
    if read is None and cache_root is None:
        cache_root = bar_cache.default_root()
    with ThreadPoolExecutor(min(READ_THREADS, len(plans))) as pool:
        projected = list(pool.map(lambda plan: _project(plan, bar_seconds, root, read, cache_root), plans))
    read_ms = (time.perf_counter() - began) * 1000
    try:
        target.mkdir()
    except FileExistsError as error:
        raise HistoricalChartError("output_exists", "Output was already claimed") from error
    (target / "bars").mkdir()
    selected, sources = [], []
    for index, (plan, (bars, info)) in enumerate(zip(plans, projected, strict=True), 1):
        projection = target / "bars" / f"{index:02d}.json"
        _write_json(projection, {"day": plan["day"], "ticker": plan["symbol"], "time_zone": "America/New_York",
                                 "s_semantics": "second_START", "bar_seconds": bar_seconds,
                                 "price_units": "raw_same_session_" + plan["day"],
                                 "observed_source_start_s": plan["start_s"],
                                 "observed_source_end_exclusive_s": plan["end_s"], "bars": bars})
        selected.append({"day": plan["day"], "ticker": plan["symbol"], "bar_seconds": bar_seconds,
                         "annotations": plan["annotations"],
                         "bar_projection": {"path": str(projection), "sha256": file_sha256(projection)}})
        sources.append(info)
    selection = target / "selection.json"
    _write_json(selection, {"schema_version": 1, "kind": "historical_ohlcv", "family": family,
                            "selected": selected})
    receipt = {"selection_path": str(selection), "selection_sha256": file_sha256(selection),
               "selected_count": len(selected), "bar_seconds": bar_seconds, "family": family,
               "bars": sum(len(bars) for bars, _ in projected), "sources": sources,
               "read_ms": read_ms, "resolve_freeze_ms": (time.perf_counter() - began) * 1000}
    _write_json(target / "provenance.json", receipt)
    return receipt


def export_trades(trades: Any, output: Path, massive_root: Path, gateway_root: Path, *, samples: int = 0,
                  warm_idle_seconds: int | None = None, **options: Any) -> dict[str, Any]:
    """``warm_idle_seconds`` draws through the gateway's warm renderer (started if none is running)."""
    began = time.perf_counter()
    gateway, script = checked_gateway(gateway_root, samples)
    receipt = resolve_trade_bundle(trades, output, massive_root, **options)
    return run_native_export(receipt, gateway, script, samples, began, warm_idle_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["export"])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--trades-json", help="the trade list as JSON text")
    source.add_argument("--trades-file", type=Path, help="a .json file holding the trade list")
    parser.add_argument("--output", type=Path, required=True, help="a new folder")
    parser.add_argument("--massive-root", type=Path, required=True, help=f"the Massive root holding {TRADES_DATASET}")
    parser.add_argument("--gateway-root", type=Path, default=REPO, help="the approved Nova checkout (default: this)")
    parser.add_argument("--bar-seconds", type=int, default=10, choices=BAR_SECONDS)
    parser.add_argument("--before", type=int, default=300, help="seconds of chart before the first entry")
    parser.add_argument("--after", type=int, default=120, help="seconds of chart after the last exit")
    parser.add_argument("--family", default=None, help="the gallery title")
    parser.add_argument("--samples", type=int, choices=range(51), default=0)
    parser.add_argument("--warm", action="store_true",
                        help="draw with the warm renderer (tools/nova_chart_warm.py), starting one if needed")
    parser.add_argument("--idle-seconds", type=int, default=600,
                        help="with --warm: a renderer this call starts stops after this long without a job")
    args = parser.parse_args(argv)
    try:
        text = args.trades_json if args.trades_json is not None else args.trades_file.read_text(encoding="utf-8")
        trades = json.loads(text)
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": {"code": "invalid_trades", "message": str(error)}}))
        return 2
    try:
        result = export_trades(trades, args.output, args.massive_root, args.gateway_root, samples=args.samples,
                               warm_idle_seconds=args.idle_seconds if args.warm else None,
                               bar_seconds=args.bar_seconds, before_s=args.before, after_s=args.after,
                               family=args.family)
    except HistoricalChartError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
