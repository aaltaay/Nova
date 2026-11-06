"""The cross-stock scan subcommands of ``tools/market_data.py`` (ADR 059), split along the same seam as the MCP's
``nova_data_scans.py``: who filed an SEC form in a span of days, every stock's FINRA short interest at one settlement,
and every listed company in an SIC industry. ``add_parsers`` registers them; ``HANDLERS`` runs them.

  py -3 tools/market_data.py sec-filings-scan 424B5 2026-09-08 2026-09-14
  py -3 tools/market_data.py sec-filings-scan S-1,S-1/A 2021-01-01 2021-01-31 --sic 2834,2836 --out s1.parquet
  py -3 tools/market_data.py short-interest-scan --day 2026-10-02 --min-shares 5000000 --min-days-to-cover 5
  py -3 tools/market_data.py short-interest-scan --settlement 2026-09-15 --kinds all --sort days_to_cover
  py -3 tools/market_data.py sector-scan --sic 283* --exchange XNAS
  py -3 tools/market_data.py sector-scan --words pharmaceutical
"""
from __future__ import annotations


def _list(raw: str | None) -> list[str] | None:
    return [part.strip() for part in raw.split(",") if part.strip()] if raw else None


def cmd_sec_filings_scan(args, show) -> int:
    from market_reads import sec_scan
    return show(sec_scan.filings_scan(_list(args.forms), args.date_from, args.date_to, _list(args.tickers),
                                      _list(args.ciks), _list(args.sic)), args)


def cmd_short_interest_scan(args, show) -> int:
    from market_reads import reference_scans
    return show(reference_scans.short_interest_scan(args.settlement, args.day, args.at, args.min_shares,
                                                    args.min_days_to_cover, _list(args.kinds), args.sort), args)


def cmd_sector_scan(args, show) -> int:
    from market_reads import reference_scans
    active = None if args.active is None else args.active == "yes"
    return show(reference_scans.sector_scan(_list(args.sic), _list(args.words), _list(args.exchange), active,
                                            _list(args.kinds)), args)


HANDLERS = {"sec-filings-scan": cmd_sec_filings_scan, "short-interest-scan": cmd_short_interest_scan,
            "sector-scan": cmd_sector_scan}


def add_parsers(sub, output) -> None:
    filings = sub.add_parser("sec-filings-scan", help="every SEC filing of FORMS filed FROM..TO (at most 31 days) "
                                                      "by the listed companies")
    filings.add_argument("forms", help="comma list, matched exactly: 424B5 / S-1,S-1/A / 8-K ...")
    filings.add_argument("date_from", help="YYYY-MM-DD")
    filings.add_argument("date_to", help="YYYY-MM-DD, at most 31 days after date_from")
    filings.add_argument("--tickers", help="comma list: only the companies that held these on date_from / date_to")
    filings.add_argument("--ciks", help="comma list of SEC CIKs (also companies outside Massive's ticker list)")
    filings.add_argument("--sic", help="comma list of SEC SIC codes (2834) or prefixes (283*), today's code")
    output(filings)
    short = sub.add_parser("short-interest-scan", help="every stock's FINRA short interest at one settlement")
    short.add_argument("--settlement", help="YYYY-MM-DD: this settlement")
    short.add_argument("--day", help="YYYY-MM-DD: the newest settlement published by this day (8 business days lag)")
    short.add_argument("--at", default="09:30", help="ET HH:MM on --day")
    short.add_argument("--min-shares", dest="min_shares", type=float, help="shares short, at least")
    short.add_argument("--min-days-to-cover", dest="min_days_to_cover", type=float, help="days to cover, at least")
    short.add_argument("--kinds", help="common (default), all, or a comma list of types (CS,ADRC,ETF ...)")
    short.add_argument("--sort", default="short_interest", choices=["short_interest", "days_to_cover", "ticker"])
    output(short)
    sector = sub.add_parser("sector-scan", help="every listed company by SIC code or SIC description words (latest)")
    sector.add_argument("--sic", help="comma list of SIC codes (2834) or prefixes (283*)")
    sector.add_argument("--words", help="comma list: a SIC description containing any (pharmaceutical)")
    sector.add_argument("--exchange", help="comma list of primary exchanges (XNAS,XNYS,XASE ...)")
    sector.add_argument("--active", choices=["yes", "no"])
    sector.add_argument("--kinds", help="common (default), all, or a comma list of types (CS,ADRC,WARRANT ...)")
    output(sector)
