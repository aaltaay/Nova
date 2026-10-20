"""The relative-volume subcommands of ``tools/market_data.py`` (#1100), split along the same seam as the MCP's
``nova_data_rvol.py``: every stock-day at a clock time, the first minute over a line, and what came next. The reads
are ``research/market_reads/rvol.py`` and ``rvol_outcomes.py``; the table is built by ``research/rvol/build_rvol.py``.

  py -3 tools/market_data.py rvol 09:30 date_from=2021-01-01 date_to=2021-12-31 price_min=1 price_max=20 rvol_min=5
  py -3 tools/market_data.py rvol-triggers 10 date_from=2025-01-01 date_to=2025-12-31 price_min=1 price_max=20 \\
      --window 06:00-09:30 --measure cumulative
  py -3 tools/market_data.py rvol-outcomes date_from=2016-01-04 date_to=2026-10-16 price_min=1 price_max=20 \\
      --at 09:30 --up 50 --down 50 --horizon close
  py -3 tools/market_data.py rvol-outcomes date_from=2025-01-01 date_to=2025-12-31 price_min=1 price_max=20 \\
      --trigger 10 --window 06:00-08:00 --horizon days --days 5
"""
from __future__ import annotations

import json
from pathlib import Path

MEASURES = ["cumulative", "five_minute", "daily_rate"]


def _params(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        out[key] = value if key in ("date_from", "date_to", "symbol") else float(value)
    return out


def _kinds(args):
    return args.kinds.split(",") if args.kinds else None


def _print_frame(frame, args) -> int:
    meta = {k: v for k, v in frame.attrs.items() if k not in ("rules",)}
    print(json.dumps({**meta, "out": args.out}, default=str))
    if len(frame) and not args.out:
        print(frame.head(args.head).to_string(index=False))
    return 0


def cmd_rvol(args, show) -> int:
    from market_reads import rvol
    frame = rvol.scan(args.at, filters=_params(args.params), measure=args.measure, kinds=_kinds(args),
                      splits=args.splits, min_base_sessions=args.min_base_sessions, limit=args.limit,
                      to_file=Path(args.out) if args.out else None)
    return _print_frame(frame, args)


def cmd_triggers(args, show) -> int:
    from market_reads import rvol
    w0, _, w1 = args.window.partition("-")
    frame = rvol.triggers(args.rvol_min, measure=args.measure, window_from=w0, window_to=w1,
                          filters=_params(args.params), kinds=_kinds(args), splits=args.splits,
                          min_base_sessions=args.min_base_sessions, fresh=args.fresh, limit=args.limit,
                          to_file=Path(args.out) if args.out else None)
    return _print_frame(frame, args)


def cmd_outcomes(args, show) -> int:
    from market_reads import rvol_outcomes
    trigger = None
    if args.trigger is not None:
        w0, _, w1 = args.window.partition("-")
        trigger = {"rvol_min": args.trigger, "measure": args.measure, "window_from": w0, "window_to": w1,
                   "fresh": args.fresh}
    answer = rvol_outcomes.outcomes(
        filters=_params(args.params), at=args.at, trigger=trigger, up_pct=args.up, down_pct=args.down,
        horizon=args.horizon, days=args.days, group_by=args.group_by,
        buckets=[float(b) for b in args.buckets.split(",")] if args.buckets else None, measure=args.measure,
        kinds=_kinds(args), splits=args.splits, min_base_sessions=args.min_base_sessions,
        control=not args.no_control, to_file=Path(args.out) if args.out else None)
    print(json.dumps(answer, default=str, indent=1))
    return 0


HANDLERS = {"rvol": cmd_rvol, "rvol-triggers": cmd_triggers, "rvol-outcomes": cmd_outcomes}


def _common(p) -> None:
    p.add_argument("params", nargs="*", help="filters: date_from=, date_to=, symbol=, price_min=, price_max=, ...")
    p.add_argument("--measure", default="cumulative", choices=MEASURES)
    p.add_argument("--kinds", help="comma list of CS,ADRC,unknown (default CS,ADRC)")
    p.add_argument("--splits", default="exclude_likely", choices=["exclude_likely", "include", "only_suspects"])
    p.add_argument("--min-base-sessions", dest="min_base_sessions", type=int, default=20)
    p.add_argument("--fresh", action="store_true",
                   help="triggers: leave out stock-days already over the line before the window opened")


def add_parsers(sub, output) -> None:
    scan = sub.add_parser("rvol", help="every stock-day's relative volume as of an ET clock time")
    scan.add_argument("at", help="ET HH:MM: bars starting before it")
    _common(scan)
    scan.add_argument("--limit", type=int)
    output(scan)
    trig = sub.add_parser("rvol-triggers", help="the first minute each stock-day crossed a relative-volume line")
    trig.add_argument("rvol_min", type=float, help="ratio: 5 = five times the baseline")
    _common(trig)
    trig.add_argument("--window", default="04:00-16:00", help="ET HH:MM-HH:MM (end exclusive)")
    trig.add_argument("--limit", type=int)
    output(trig)
    out = sub.add_parser("rvol-outcomes", help="+X%% or -X%% first, from a clock time or a trigger")
    _common(out)
    out.add_argument("--at", help="ET HH:MM: every stock-day at this clock time")
    out.add_argument("--trigger", type=float, help="rvol_min: entries are the first minute over this line")
    out.add_argument("--window", default="04:00-16:00", help="trigger window, ET HH:MM-HH:MM")
    out.add_argument("--up", type=float, default=50.0, help="percent points above the entry price")
    out.add_argument("--down", type=float, default=50.0, help="percent points below the entry price")
    out.add_argument("--horizon", default="close", choices=["close", "session", "days"])
    out.add_argument("--days", type=int, help="sessions after the entry day, with --horizon days")
    out.add_argument("--group-by", dest="group_by", choices=["rvol", "year", "hour", "none"])
    out.add_argument("--buckets", help="comma list of rvol bucket edges (default 0,1,2,3,5,10,20,50,100,1000)")
    out.add_argument("--no-control", dest="no_control", action="store_true")
    out.add_argument("--out", help="write every scored entry to this .parquet or .csv file")
