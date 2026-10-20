"""The cash-runway subcommand of ``tools/market_data.py`` (ADR 059, #1102), split along the same seam as the MCP's
``nova_data_runway.py``: a company's cash, operating cash burn, runway, share-count growth and shelf / offering
filings as known on a past day. ``add_parsers`` registers it; ``HANDLERS`` runs it.

  py -3 tools/market_data.py runway GURE 2024-03-01
  py -3 tools/market_data.py runway AAP 2016-06-01 --cik 1411579 --lookback-days 365
"""
from __future__ import annotations

import json

DEFAULT_LOOKBACK_DAYS = 1095        # == market_reads.runway.DEFAULT_LOOKBACK_DAYS (a test holds the two together)


def cmd_runway(args, show) -> int:
    from market_reads import runway
    print(json.dumps(runway.runway(args.symbol, args.day, args.cik, args.lookback_days), default=str, indent=1))
    return 0


HANDLERS = {"runway": cmd_runway}


def add_parsers(sub, output) -> None:
    runway = sub.add_parser("runway", help="cash, burn, runway, share growth and offering filings as known on DAY")
    runway.add_argument("symbol")
    runway.add_argument("day", help="YYYY-MM-DD")
    runway.add_argument("--cik", help="SEC CIK: read this company when the ticker was used by more than one")
    runway.add_argument("--lookback-days", dest="lookback_days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="offering filings filed this many days before DAY (1-3650)")
