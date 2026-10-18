"""What the front door serves, in one table an agent reads before it asks (ADR 059; the MCP's ``data_catalog``).

Each entry names the data, where it comes from, how far back it goes, the as-of rule that keeps a past day honest,
its units, and the front-door call that reads it (MCP tool / command line). ``docs/market-data.md`` is the prose.
"""
from __future__ import annotations

CATALOG = (
    {"name": "trades", "source": "Massive flat files (SIP)", "history": "2016-01-04 on, every US stock",
     "as_of": "one stock-day; raw, never split-adjusted (adjust=true for today's terms)",
     "units": "price dollars, size shares, sip_timestamp ns; sets_price = the print may move last/candles",
     "mcp": "stock_day(kind='trades')", "cli": "market_data.py trades SYMBOL DAY"},
    {"name": "quotes", "source": "Massive flat files (NBBO)", "history": "2016-01-04 on",
     "as_of": "one stock-day; Level 1 only (no depth history)", "units": "bid/ask dollars and shares",
     "mcp": "stock_day(kind='quotes')", "cli": "market_data.py quotes SYMBOL DAY"},
    {"name": "bars", "source": "Massive minute files; seconds built from trades", "history": "2016-01-04 on",
     "as_of": "one stock-day (daily bars are not a stock-day read)",
     "units": "OHLC dollars, volume shares. Volume rule: minute bars are Massive's own (its SIP volume rules); "
              "seconds bars count every trade except cancel/error records, so a minute of 10s bars can sum higher "
              "(GME 2021-01-27 09:30: 185,567 from trades vs 179,397 in the minute file, +3.4%)",
     "mcp": "stock_day(kind='bars')", "cli": "market_data.py bars SYMBOL DAY --tf 1m|5m|10s"},
    {"name": "movers_index", "source": "Nova's day movers store (built from the day files)",
     "history": "2016-01-04 on, every session (2,713 through 2026-10-16)",
     "as_of": "one row per stock-day, facts of that finished day",
     "units": "*_pct percent points (the store keeps fractions; the front door converts); prices raw prior close. "
              "Likely reverse splits are left out by default in both tools (splits=exclude_likely | include | "
              "only_suspects). float_max (movers_search) is SEC shares OUTSTANDING filed by the day, not free float",
     "mcp": "movers_search (endpoint, <=500 rows) / movers_scan (bulk: needs dates, a symbol or a limit; 100,000 "
            "rows unless limit)", "cli": "market_data.py movers key=value / scan key=value"},
    {"name": "boards", "source": "Nova's leaderboard store: recorded desk boards, else rebuilt",
     "history": "1,752 of 2,713 sessions, 2016-11-30 .. 2026-10-16, with holes (e.g. 2023-06-01, 2024-03-01); "
                "data_status has the live count",
     "as_of": "the board as it stood at the minute asked; a day with no board answers covered=false with its gap",
     "units": "change_pct / gap_pct percent points (the store keeps fractions; the front door converts)",
     "mcp": "board", "cli": "market_data.py board DAY --at HH:MM"},
    {"name": "splits", "source": "Massive split table + SEC-confirmed splits", "history": "all",
     "as_of": "factor puts a day's raw price in another day's terms, using only the splits of the company that "
              "held the ticker that day (a reused ticker lists holder_cik)",
     "units": "price_factor multiplies prices", "mcp": "splits", "cli": "market_data.py splits SYMBOL --day DAY"},
    {"name": "financials", "source": "Massive reference: balance sheets, income statements, cash flows",
     "history": "filings 2016-01 on", "as_of": "a statement counts from its filing_date; a reused ticker reads the "
                                               "company that held it on as_of (by the statements' cik)",
     "units": "dollars; balance-sheet common_stock / treasury_stock are dollars, not shares; income statement "
              "basic/diluted_shares_outstanding are the period's EPS share counts",
     "mcp": "financials", "cli": "market_data.py financials SYMBOL --as-of DAY"},
    {"name": "sec_shares", "source": "SEC companyfacts.zip (XBRL)", "history": "XBRL era (about 2009-2011 on)",
     "as_of": "a fact counts from the day it was filed; outstanding split-adjusted to the day's basis; the "
              "company is the one that held the ticker on the day (84 tickers had two companies)",
     "units": "shares outstanding (not free float); EntityPublicFloat in USD", "mcp": "sec_shares",
     "cli": "market_data.py sec-shares SYMBOL --day DAY"},
    {"name": "sec_filings", "source": "SEC submissions.zip", "history": "all EDGAR filings",
     "as_of": "a filing counts from its filing date; the company that held the ticker on as_of",
     "units": "form, filed, report_date, accession (Forms 3/4/5, 13D/13G, 10-Q/K, 20-F, 8-K, 424B ...)",
     "mcp": "sec_filings", "cli": "market_data.py sec-filings SYMBOL --as-of DAY --forms 4,8-K"},
    {"name": "float_latest", "source": "Massive /stocks/vX/float", "history": "latest only -- no past days",
     "as_of": "never point-in-time; excludes insiders, 5%+ holders, locked-up/restricted shares",
     "units": "free_float shares, free_float_percent", "mcp": "float_latest", "cli": "market_data.py float SYMBOL"},
    {"name": "ipos", "source": "Massive reference", "history": "2008 on (dump from 2016)",
     "as_of": "listing_date", "units": "prices dollars, shares offered; no lockup terms", "mcp": "ipos",
     "cli": "market_data.py ipos --symbol SYMBOL"},
    {"name": "ticker_details", "source": "Massive reference", "history": "latest only",
     "as_of": "current values as of the dump", "units": "share_class_shares_outstanding shares",
     "mcp": "ticker_details", "cli": "market_data.py ticker SYMBOL"},
    {"name": "short_interest", "source": "FINRA via Massive reference", "history": "2016 on, twice monthly",
     "as_of": "a settlement counts only after its publish lag (move_reason.short_interest)",
     "units": "shares, days_to_cover", "mcp": "short_interest", "cli": "market_data.py short-interest SYMBOL DAY"},
)
NOT_HERE = (
    "insider holdings (SEC Form 3/4/5 data sets) -- not downloaded; sec_filings lists the filings",
    "lockup terms -- no SEC dataset; 424B prospectus text or a paid vendor",
    "Level 2 / depth history from Massive -- its stock plan is Level 1 only. Nova's own IBKR recordings exist "
    "(F:\\Nova\\sim_capture: 20 sessions 2026-09-19 .. 2026-10-16; the desk cache's l2.db depth snapshots and "
    "archive.db tape_ibkr prints from 2026-07-15; F:\\Nova\\book_watch) but the front door does not serve them yet "
    "-- the Sim replays them",
    "news before 2021-04",
    "free float as of a past day -- float_latest is today's only; sec_shares is shares outstanding",
)
