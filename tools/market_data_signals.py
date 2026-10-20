"""The signal subcommands of ``tools/market_data.py``, split along the same seam as the MCP's ``nova_data_signals.py``:
the Trader's signals on past days -- the list, one stock-day minute by minute, every in-play stock at a minute, and a
test of any mix. Reads ``research/market_reads/signals.py`` and ``signal_outcomes.py``; the table is built by
``research/signals/build_signals.py``.

  py -3 tools/market_data.py signals                                   # every signal, its values and history
  py -3 tools/market_data.py signal-series SMJF 2026-10-09 --signals pillars_n,front,setup_first_pullback
  py -3 tools/market_data.py signal-scan 2026-10-09 09:45 --when "pillars_n>=4" --when "front=Front side"
  py -3 tools/market_data.py signal-test date_from=2024-01-01 date_to=2024-12-31 --when "pillars_n>=4" \\
      --when "setup_first_pullback=triggered" --window 07:00-10:30 --up 20 --down 10

A ``--when`` is ``signal>=number``, ``signal<=number`` or ``signal=value`` (``|`` between values; ``true`` /
``false`` for a yes-or-no signal).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CONDITION = re.compile(r"^\s*([a-z0-9_]+)\s*(>=|<=|=)\s*(.+?)\s*$")


def _params(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        out[key] = value if key in ("date_from", "date_to", "symbol") else float(value)
    return out


def conditions(texts: list[str] | None) -> list[dict]:
    """``--when`` texts as ``signal_test``'s conditions (``signal_registry.check`` then holds them to the list)."""
    from market_reads.signal_registry import BY_COLUMN
    out = []
    for text in texts or []:
        found = CONDITION.match(text)
        if not found:
            raise SystemExit(f"--when {text!r}: write signal>=number, signal<=number or signal=value")
        name, op, value = found.groups()
        kind = BY_COLUMN[name].kind if name in BY_COLUMN else None
        if op == ">=":
            out.append({"signal": name, "min": float(value)})
        elif op == "<=":
            out.append({"signal": name, "max": float(value)})
        else:
            values = [v.strip() for v in value.split("|")]
            if kind == "bool":
                if any(v.lower() not in ("true", "false") for v in values):
                    raise SystemExit(f"--when {text!r}: {name} is true or false")
                values = [v.lower() == "true" for v in values]
            out.append({"signal": name, "is": values if len(values) > 1 else values[0]})
    return out


def _show(frame, args) -> int:
    if args.out:
        path = Path(args.out)
        frame.to_parquet(path, index=False) if path.suffix == ".parquet" else frame.to_csv(path, index=False)
    print(json.dumps({"rows": len(frame), "out": args.out}))
    if len(frame) and not args.out:
        print(frame.head(args.head).to_string(index=False))
    return 0


def cmd_catalog(args, show) -> int:
    from market_reads import signal_registry, signals_store
    print(json.dumps({"signals": signal_registry.catalog(), "not_rebuilt": signal_registry.NOT_REBUILT,
                      "table": signals_store.status()}, indent=1, default=str))
    return 0


def cmd_series(args, show) -> int:
    from market_reads import signals
    return _show(signals.series(args.symbol, args.day, args.signals.split(",") if args.signals else None,
                                args.start, args.end), args)


def cmd_scan(args, show) -> int:
    from market_reads import signals
    return _show(signals.scan(args.day, args.at, conditions(args.when) or None), args)


def cmd_test(args, show) -> int:
    from market_reads import signal_outcomes
    w0, _, w1 = args.window.partition("-")
    answer = signal_outcomes.test(when=conditions(args.when), filters=_params(args.params), window_from=w0,
                                  window_to=w1, fresh=args.fresh, up_pct=args.up, down_pct=args.down,
                                  horizon=args.horizon, days=args.days, group_by=args.group_by,
                                  control=not args.no_control, to_file=Path(args.out) if args.out else None)
    print(json.dumps(answer, default=str, indent=1))
    return 0


HANDLERS = {"signals": cmd_catalog, "signal-series": cmd_series, "signal-scan": cmd_scan, "signal-test": cmd_test}


def add_parsers(sub, output) -> None:
    sub.add_parser("signals", help="every signal of the Trader's panel the signal table holds")
    series = sub.add_parser("signal-series", help="one in-play stock-day's signals minute by minute")
    series.add_argument("symbol")
    series.add_argument("day")
    series.add_argument("--signals", help="comma list of signal names (default all)")
    series.add_argument("--start", help="ET HH:MM: the first minute")
    series.add_argument("--end", help="ET HH:MM: up to this minute (exclusive)")
    output(series)
    scan = sub.add_parser("signal-scan", help="every in-play stock at an ET minute, with its signals")
    scan.add_argument("day")
    scan.add_argument("at", help="ET HH:MM: the minute before it, as of its end")
    scan.add_argument("--when", action="append", help="a condition (repeat: all must hold)")
    output(scan)
    test = sub.add_parser("signal-test", help="+X%% or -X%% first after a mix of signals all held")
    test.add_argument("params", nargs="*", help="filters: date_from=, date_to=, symbol=, price_min=, price_max=")
    test.add_argument("--when", action="append", required=True, help="a condition (repeat: all must hold)")
    test.add_argument("--window", default="04:00-16:00", help="ET HH:MM-HH:MM (end exclusive)")
    test.add_argument("--fresh", action="store_true", help="leave out stock-days where it all held before the window")
    test.add_argument("--up", type=float, default=20.0, help="percent points above the entry price")
    test.add_argument("--down", type=float, default=20.0, help="percent points below the entry price")
    test.add_argument("--horizon", default="close", choices=["close", "session", "days"])
    test.add_argument("--days", type=int, help="sessions after the entry day, with --horizon days")
    test.add_argument("--group-by", dest="group_by", default="year", choices=["year", "hour", "none"])
    test.add_argument("--no-control", dest="no_control", action="store_true")
    test.add_argument("--out", help="write every scored entry to this .parquet or .csv file")
