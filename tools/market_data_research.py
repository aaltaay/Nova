"""The momentum-research subcommands of ``tools/market_data.py`` (ADR 059), split along the same seam as the MCP's
``nova_data_research.py``: find stock-days, daily bars, the market around a day, one stock-day's stats, order flow,
halts, catalysts, news across stocks and symbols. ``add_parsers`` registers them; ``HANDLERS`` runs them.

  py -3 tools/market_data.py find date_from=2025-01-01 date_to=2025-03-31 price_min=2 price_max=20 high_min=50 --float-max 20000000
  py -3 tools/market_data.py find date_from=2026-09-01 date_to=2026-09-30 high_min=100 --sort high --limit 10
  py -3 tools/market_data.py find date_from=2026-09-01 date_to=2026-09-30 kinds=all     (warrants, rights, ETFs too)
  py -3 tools/market_data.py daily GME 2021-01-04 2021-02-26
  py -3 tools/market_data.py context 2026-09-09
  py -3 tools/market_data.py stats IRD 2026-09-09
  py -3 tools/market_data.py flow IRD 2026-09-09 --bucket 5m
  py -3 tools/market_data.py halts --symbol GME --from 2021-01-25 --to 2021-01-29
  py -3 tools/market_data.py catalysts IRD --from 2026-09-08 --to 2026-09-09
  py -3 tools/market_data.py news --from 2021-11-01 --to 2021-12-31 --category fda_regulatory --words approv,clear
  py -3 tools/market_data.py halts --from 2026-09-01 --to 2026-09-05 --codes news
  py -3 tools/market_data.py symbols aurora | symbols --ticker AAP --day 2016-06-01
"""
from __future__ import annotations

import json


def _list(raw: str | None) -> list[str] | None:
    return raw.split(",") if raw else None


def _print(answer) -> int:
    print(json.dumps(answer, default=str, indent=1))
    return 0


def cmd_find(args, show) -> int:
    from market_reads import stock_days
    params = dict(pair.split("=", 1) for pair in args.params)
    symbol = params.pop("symbol", None)
    kinds = params.pop("kinds", None)
    frame = stock_days.find_stock_days(
        filters=params, symbol=symbol, kinds=kinds.split(",") if kinds else None, splits=args.splits,
        float_max=args.float_max, outstanding_max=args.outstanding_max, float_basis=args.float_basis,
        float_unknown=args.float_unknown, catalyst=args.catalyst.split(",") if args.catalyst else None,
        halted=None if args.halted is None else args.halted == "yes", sort=args.sort, limit=args.limit,
        cursor=args.cursor, page_size=args.page_size, to_file=bool(args.out),
        catalyst_category=args.catalyst_category.split(",") if args.catalyst_category else None,
        catalyst_words=args.catalyst_words.split(",") if args.catalyst_words else None,
        rvol_daily_min=args.rvol_daily_min, halt_codes=_list(args.halt_codes))
    return show(frame, args)


def cmd_daily(args, show) -> int:
    from market_reads import daily
    return show(daily.daily_bars(args.symbol, args.date_from, args.date_to, args.adjust, args.as_of), args)


def cmd_context(args, show) -> int:
    from market_reads import daily
    extra = {"symbols": tuple(args.symbols.split(","))} if args.symbols else {}
    return _print(daily.market_context(args.day, **extra))


def cmd_stats(args, show) -> int:
    from market_reads import stats
    return _print(stats.stock_day_stats(args.symbol, args.day, args.rvol_days, not args.no_spread))


def cmd_flow(args, show) -> int:
    from market_reads import order_flow
    return show(order_flow.order_flow(args.symbol, args.day, args.start, args.end, args.bucket), args)


def cmd_halts(args, show) -> int:
    from market_reads import halts
    return show(halts.halts(args.symbol, args.day, args.date_from, args.date_to, args.source,
                            _list(args.codes)), args)


def cmd_catalysts(args, show) -> int:
    from market_reads import catalysts
    if args.verdicts:
        return show(catalysts.verdicts(symbol=args.symbol, date_from=args.date_from, date_to=args.date_to), args)
    sources = args.sources.split(",") if args.sources else None
    return show(catalysts.items(args.symbol, args.date_from, args.date_to, args.at, sources, args.limit), args)


def cmd_news(args, show) -> int:
    from market_reads import catalysts
    if args.items:
        return show(catalysts.search_items(args.date_from, args.date_to, _list(args.words) or [],
                                           _list(args.sources), args.limit), args)
    return show(catalysts.search_verdicts(args.date_from, args.date_to, _list(args.verdict), _list(args.category),
                                          _list(args.words), args.limit), args)


def cmd_symbols(args, show) -> int:
    from market_reads import symbols
    if args.ticker:
        return _print(symbols.symbol(args.ticker, args.day))
    active = None if args.active is None else args.active == "yes"
    types = args.types.split(",") if args.types else None
    return show(symbols.search(args.query, active=active, types=types, exchange=args.exchange, cik=args.cik,
                               limit=args.limit), args)


HANDLERS = {"find": cmd_find, "daily": cmd_daily, "context": cmd_context, "stats": cmd_stats, "flow": cmd_flow,
            "halts": cmd_halts, "catalysts": cmd_catalysts, "news": cmd_news, "symbols": cmd_symbols}


def add_parsers(sub, output) -> None:
    find = sub.add_parser("find", help="stock-days with shares known that day, catalyst, halts (key=value filters)")
    find.add_argument("params", nargs="*", help="movers filters: date_from=, price_min=, high_min= ... symbol=, "
                      "kinds= (default common stock; kinds=all, kinds=ETF,CS)")
    find.add_argument("--splits", default="exclude_likely", choices=["exclude_likely", "include", "only_suspects"])
    find.add_argument("--float-max", dest="float_max", type=float, help="shares; on --float-basis")
    find.add_argument("--outstanding-max", dest="outstanding_max", type=float,
                      help="shares: --float-max under the name of what it filters (SEC shares outstanding)")
    find.add_argument("--float-basis", dest="float_basis", default="sec_outstanding",
                      choices=["sec_outstanding", "enrichment", "best"])
    find.add_argument("--float-unknown", dest="float_unknown", default="exclude", choices=["exclude", "include", "only"])
    find.add_argument("--catalyst", help="comma list of verdicts to keep (catalyst, none_found, unknown ...)")
    find.add_argument("--catalyst-category", dest="catalyst_category",
                      help="comma list of verdict categories to keep (fda_regulatory, clinical_data ...)")
    find.add_argument("--catalyst-words", dest="catalyst_words",
                      help="comma list: keep a headline containing any (approv,clear); a text match")
    find.add_argument("--rvol-daily-min", dest="rvol_daily_min", type=float,
                      help="ratio: the day's volume over its usual whole-session volume (5 = 5x); unknowns left out")
    find.add_argument("--halted", choices=["yes", "no"])
    find.add_argument("--halt-codes", dest="halt_codes",
                      help="comma list: keep a day with a halt of any code (T1,LUDP ...; news or luld for the groups)")
    find.add_argument("--sort", choices=["newest", "oldest", "high", "low", "close", "gap", "volume", "dollar_volume"],
                      help="rank the rows like the movers search (default: oldest day first)")
    find.add_argument("--cursor", help="next_cursor of the previous page (same arguments)")
    find.add_argument("--page-size", dest="page_size", type=int, help="rows per page (default 200)")
    find.add_argument("--limit", type=int, help="the same as --page-size, under the movers search's name")
    output(find)
    daily = sub.add_parser("daily", help="daily bars for a date range (raw; --adjust for split terms)")
    daily.add_argument("symbol")
    daily.add_argument("date_from")
    daily.add_argument("date_to")
    daily.add_argument("--adjust", action="store_true")
    daily.add_argument("--as-of", dest="as_of")
    output(daily)
    context = sub.add_parser("context", help="SPY / QQQ / IWM around a day")
    context.add_argument("day")
    context.add_argument("--symbols", help="comma list instead of SPY,QQQ,IWM")
    stats = sub.add_parser("stats", help="one stock-day's premarket, open, VWAP, spread, relative volume")
    stats.add_argument("symbol")
    stats.add_argument("day")
    stats.add_argument("--rvol-days", dest="rvol_days", type=int, default=20)
    stats.add_argument("--no-spread", dest="no_spread", action="store_true", help="skip the quote read")
    flow = sub.add_parser("flow", help="per-minute order flow (trades_flow_v1)")
    flow.add_argument("symbol")
    flow.add_argument("day")
    flow.add_argument("--from", dest="start", help="ET HH:MM, inclusive")
    flow.add_argument("--to", dest="end", help="ET HH:MM, exclusive")
    flow.add_argument("--bucket", default="1m", choices=["1m", "5m", "15m", "30m", "60m", "day"])
    output(flow)
    halt = sub.add_parser("halts", help="trading halts by symbol / day")
    halt.add_argument("--symbol")
    halt.add_argument("--day")
    halt.add_argument("--from", dest="date_from")
    halt.add_argument("--to", dest="date_to")
    halt.add_argument("--source")
    halt.add_argument("--codes", help="comma list: T1,T12,LUDP ... or news / luld for their groups")
    output(halt)
    cat = sub.add_parser("catalysts", help="news items naming a stock (or --verdicts) in a window")
    cat.add_argument("symbol")
    cat.add_argument("--from", dest="date_from")
    cat.add_argument("--to", dest="date_to")
    cat.add_argument("--at", help="'YYYY-MM-DD HH:MM' ET: only items published by then")
    cat.add_argument("--sources", help="comma list: edgar,alpaca,finnhub,massive")
    cat.add_argument("--limit", type=int)
    cat.add_argument("--verdicts", action="store_true", help="the catalyst verdicts instead of the items")
    output(cat)
    news = sub.add_parser("news", help="news across every stock in a date range: verdicts (default) or --items")
    news.add_argument("--from", dest="date_from", required=True)
    news.add_argument("--to", dest="date_to", required=True)
    news.add_argument("--verdict", help="comma list: catalyst,negative,routine_only,noise_only,none_found")
    news.add_argument("--category", help="comma list of verdict categories (fda_regulatory ...)")
    news.add_argument("--words", help="comma list: a headline containing any (a text match)")
    news.add_argument("--items", action="store_true", help="headlines (needs --words) instead of verdicts")
    news.add_argument("--sources", help="with --items, comma list: edgar,alpaca,finnhub,massive")
    news.add_argument("--limit", type=int)
    output(news)
    sym = sub.add_parser("symbols", help="find a stock by ticker or name; --ticker for one ticker's history")
    sym.add_argument("query", nargs="?")
    sym.add_argument("--ticker")
    sym.add_argument("--day", help="with --ticker: which company held it that day")
    sym.add_argument("--active", choices=["yes", "no"])
    sym.add_argument("--types", help="comma list: CS,ADRC,ETF ...")
    sym.add_argument("--exchange", help="primary exchange, e.g. XNAS")
    sym.add_argument("--cik", help="every ticker a company used")
    sym.add_argument("--limit", type=int, default=50)
    output(sym)
