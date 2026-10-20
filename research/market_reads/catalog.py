"""What the front door serves, in one table an agent reads before it asks (ADR 059; the MCP's ``data_catalog``).

Each entry names the data, where it comes from, how far back it goes, the as-of rule that keeps a past day honest,
its units, and the front-door call that reads it (MCP tool / command line). ``docs/market-data.md`` is the prose.
"""
from __future__ import annotations

# The momentum-research reads (stock_days, daily, stats, order_flow, halts, catalysts, symbols).
RESEARCH = (
    {"name": "stock_days", "source": "movers index + movers sec_shares + desk enrichment snapshots + catalyst "
                                     "verdicts + halt log", "history": "2016-01-04 on (each join has its own reach)",
     "as_of": "shares filed by the day (as of <= 120 days, split-adjusted); the desk's float that day; the "
              "verdict for the day; likely splits left out like movers_search",
     "units": "*_pct percent points; float_shares labelled by float_source (sec_shares_outstanding = outstanding, "
              "NOT free float; enrichment_snapshot = the desk's float, 2026-07-28 on); *_et ET HH:MM",
     "mcp": "find_stock_days (pages: next_cursor)", "cli": "market_data.py find key=value --float-max N"},
    {"name": "daily_bars", "source": "Massive day files (day_aggs_v1)", "history": "2016-01-04 on, 2,713 days",
     "as_of": "one row per session the stock traded; raw unless adjust (splits of the day's company)",
     "units": "OHLC dollars; volume = the whole 04:00-20:00 session with odd lots, prices regular hours; "
              "change / gap / range percent points", "mcp": "daily_bars / market_context (SPY, QQQ, IWM)",
     "cli": "market_data.py daily SYMBOL FROM TO / context DAY"},
    {"name": "stock_day_stats", "source": "computed on demand from minute bars, day files and NBBO quotes",
     "history": "2016-01-04 on", "as_of": "one stock-day; relative volume against prior sessions only",
     "units": "raw dollars and shares; spread cents and bps; methods stated in the answer's rules",
     "mcp": "stock_day_stats", "cli": "market_data.py stats SYMBOL DAY"},
    {"name": "order_flow", "source": "trades_flow_v1: one row per ticker-minute built from every trade "
                                     "(research/massive_builders)", "history": "2016 on, 2,712 days",
     "as_of": "one stock-day, per minute (ET)",
     "units": "shares / dollars / counts; *_pct percent points of volume; off exchange = FINRA TRF (exchange 4); "
              "retail by the sub-penny rule (a lower bound); definitions docs/massive-builders.md",
     "mcp": "order_flow", "cli": "market_data.py flow SYMBOL DAY --bucket 5m"},
    {"name": "halts", "source": "Nova's halt log (leaderboard store: Nasdaq Trade Halt RSS + IBKR)",
     "history": "Nasdaq 2021-09-21 on (backfill to 2026-09-21, the desk's poll after); a resumption whose start "
                "is not logged has start_ts null; IBKR 2026-09-23 on, desk-streamed symbols only; "
                "before 2021-09-21 not covered (halts null, never 0)",
     "as_of": "a halt counts at its start; times ET",
     "units": "start / end ET, duration seconds, code (LUDP = LULD pause, M volatility pause, T1 / T12 news "
              "pending, T3 a resolved news halt)", "mcp": "halts", "cli": "market_data.py halts --symbol S --day D"},
    {"name": "catalysts", "source": "Nova's catalyst backfill (EDGAR, Alpaca, Finnhub, Massive news) and its "
                                    "verdicts", "history": "items: only tickers the backfill targeted; Massive news "
                                                           "nearly empty before 2021-04; Finnhub 2025 on. verdicts "
                                                           "2021-10-11 .. 2026-09-21 (Five Pillars gap universe; "
                                                           "2026-06-17 on also leaderboard top-10 $1-$20)",
     "as_of": "an item counts from its published time (at= cuts look-ahead); a verdict reads the window from the "
              "prior 16:00 ET close to its target's cutoff (cutoff_et: 09:30, or the first top-10 minute); stored "
              "verdicts are rules v7 (the live classifier is newer: meta.warning)",
     "units": "published ET; verdict / category / strength labels; a missing verdict is unknown, never no news",
     "mcp": "catalysts", "cli": "market_data.py catalysts SYMBOL --from DAY --to DAY [--verdicts]"},
    {"name": "symbols", "source": "Massive ticker list (reference/tickers.json: 36,729 rows, 13,252 active)",
     "history": "latest dump (delisted tickers included)",
     "as_of": "which company held a ticker on a day: tickers.py (84 tickers had two companies)",
     "units": "ticker, name, cik, type, exchange, active / delisted", "mcp": "symbols",
     "cli": "market_data.py symbols QUERY / symbols --ticker T --day DAY"},
)

# Nova's own recordings of IBKR's live feed (recordings.py): the desk's stores, read-only; Massive has no Level 2.
RECORDINGS = (
    {"name": "recorded_depth", "source": "Nova's Session Records (sim_capture l2.jsonl) and the desk cache's l2.db "
                                         "depth snapshots", "history": "Session Records 2026-09-19 on (symbols the "
                                                                       "operator or auto-record recorded, at most 3 "
                                                                       "at once); l2.db from the desk's depth "
                                                                       "sessions",
     "as_of": "the newest book at or before the ET moment asked, no older than max_age_sec; a Session Record is never "
              "read across a gap; l2.db skips top-of-book-only rows; auto serves the newer store",
     "units": "price dollars, size shares, ts epoch seconds on Nova's receive clock, *_et Eastern; books best price "
              "first, the recorder keeps at most 50 a second (coverage.fidelity counts the rest); covered=false is "
              "unrecorded, never an empty book",
     "mcp": "recorded_depth", "cli": "market_data.py recorded-depth SYMBOL DAY --at HH:MM[:SS]"},
    {"name": "recorded_tape", "source": "Nova's Session Records (sim_capture prints.jsonl) and the desk cache's "
                                        "archive.db tape_ibkr", "history": "Session Records 2026-09-19 on; archive "
                                                                           "2026-07-15 on, every print the desk's "
                                                                           "tape line saw for any symbol",
     "as_of": "prints in an ET window [start, end), oldest first; auto serves a Session Record when one exists for "
              "the symbol-day (its gaps are stated and may hold prints the archive has), else the archive",
     "units": "price dollars, size shares; ts / receive_ts epoch seconds -- ts is when Nova RECEIVED the print, "
              "exchange_ts IBKR's own second (Session Records only); side (ask | bid | between | unknown) / bid / ask "
              "the desk's own judgement at receipt, unknown when no usable book; sets_price judged from conditions alone in the archive",
     "mcp": "recorded_tape (rows: meta.capped)", "cli": "market_data.py recorded-tape SYMBOL DAY --from HH:MM --to HH:MM"},
)

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
    *RESEARCH,
    *RECORDINGS,
)
NOT_HERE = (
    "insider holdings (SEC Form 3/4/5 data sets) -- not downloaded; sec_filings lists the filings",
    "lockup terms -- no SEC dataset; 424B prospectus text or a paid vendor",
    "Level 2 / depth history from Massive -- its stock plan is Level 1 only; Nova's own recorded books are "
    "recorded_depth (only symbols Nova recorded or the desk watched, from 2026-09-19 / 2026-07-15)",
    "the book watcher's marks (F:\\Nova\\book_watch) and the Session Records' recorded quotes -- recorded, not "
    "served yet (#1103); the Sim replays them",
    "news before 2021-04",
    "free float as of a past day -- float_latest is today's only; sec_shares is shares outstanding",
)
