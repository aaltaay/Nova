"""The cross-stock scans of the nova-data MCP server (ADR 059): who filed an SEC form in a span of days, every stock's
FINRA short interest at one settlement, and every listed company in an SIC industry.

Split from ``tools/nova_data_mcp.py`` along the tool-set seam, like ``nova_data_research.py``: ``ScanTools`` holds the
bodies, ``register`` their MCP descriptions. The one-stock reads stay there (``sec_filings``, ``short_interest``,
``ticker_details``); the methods are ``research/market_reads/sec_scan.py`` and ``reference_scans.py``. Same contract:
read-only on the data, a table answer holds 200 rows inline, ``output_name`` writes a new file.
"""
from __future__ import annotations

from typing import Any

PRELOAD = ("market_reads.sec_scan", "market_reads.reference_scans")
MAX_SPAN_DAYS = 31          # == market_reads.sec_scan.MAX_SPAN_DAYS (a test holds the two together)


class ScanTools:
    """Tool bodies; the host class gives ``output_path`` and ``answer`` (``nova_data_mcp.table_answer``)."""

    def sec_filings_scan(self, forms: list[str], date_from: str, date_to: str, tickers: list[str] | None = None,
                         ciks: list[str] | None = None, sic: list[str] | None = None,
                         output_name: str | None = None) -> dict[str, Any]:
        from market_reads import sec_scan
        out = self.output_path(output_name)
        return self.answer(sec_scan.filings_scan(forms, date_from, date_to, tickers, ciks, sic), out)

    def short_interest_scan(self, settlement: str | None = None, day: str | None = None, at: str = "09:30",
                            min_shares: float | None = None, min_days_to_cover: float | None = None,
                            kinds: list[str] | None = None, sort: str = "short_interest",
                            output_name: str | None = None) -> dict[str, Any]:
        from market_reads import reference_scans
        out = self.output_path(output_name)
        return self.answer(reference_scans.short_interest_scan(settlement, day, at, min_shares, min_days_to_cover,
                                                               kinds, sort), out)

    def sector_scan(self, sic: list[str] | None = None, sic_words: list[str] | None = None,
                    exchange: list[str] | None = None, active: bool | None = None, kinds: list[str] | None = None,
                    output_name: str | None = None) -> dict[str, Any]:
        from market_reads import reference_scans
        out = self.output_path(output_name)
        return self.answer(reference_scans.sector_scan(sic, sic_words, exchange, active, kinds), out)


def register(server, service, run, reads, writes_file) -> None:
    """The three tools on ``server`` (``run`` executes a body off the event loop; heavy ones one at a time)."""

    @server.tool(annotations=writes_file)
    async def sec_filings_scan(forms: list[str], date_from: str, date_to: str, tickers: list[str] | None = None,
                               ciks: list[str] | None = None, sic: list[str] | None = None,
                               output_name: str | None = None) -> dict:
        """Who filed a form, across companies: every SEC filing of forms (required, matched exactly: ["424B5"],
        ["S-1", "S-1/A"], ["8-K"], ["SC 13D", "SCHEDULE 13D"]) filed date_from..date_to (YYYY-MM-DD, required, at most
        31 days). Reads SEC's submissions.zip company by company -- every company in Massive's ticker list, active
        and delisted (a filer that never held a ticker Massive lists is not read unless ciks names it): about 7 s for
        a week, up to ~18 s for a broad form over a month, ~10 s more on a server's first SEC read; tickers (the
        company that held each on date_from and date_to), ciks or sic (SEC's own code today: "2834", or "283*" a
        prefix) narrow it. Rows: filed, accepted_et (SEC's acceptance time on its own clock, ET; accepted_clock says
        what placed it), form, ticker (the ticker the company held on the filing day, null before its listing),
        tickers (every ticker Massive gives the CIK), cik, company, sic, accession, report_date, items (8-K item
        numbers). A Form 4 or Schedule 13D/G is listed under the subject company too: each row names its own cik.
        Lists filings, not their contents; meta.scanned counts what was read. output_name (new .parquet/.csv) for all
        rows."""
        return await run(service.sec_filings_scan, forms, date_from, date_to, tickers, ciks, sic, output_name)

    @server.tool(annotations=writes_file)
    async def short_interest_scan(settlement: str | None = None, day: str | None = None, at: str = "09:30",
                                  min_shares: float | None = None, min_days_to_cover: float | None = None,
                                  kinds: list[str] | None = None, sort: str = "short_interest",
                                  output_name: str | None = None) -> dict:
        """Which stocks had short interest of at least min_shares shares and / or min_days_to_cover days, at ONE
        FINRA settlement: settlement (YYYY-MM-DD, twice a month) or the newest one published by day at ET HH:MM --
        the same publish lag as short_interest (a settlement counts from its 8th business day; meta.picked names it,
        and the newer one still pending). Every row is that settlement's: a stock missing from it is missing, never
        read from an older one. COMMON STOCK (CS, ADRC) by default; kinds ["all"] keeps ETFs, preferreds, warrants
        and OTC names Massive's list does not type (meta.left_out counts what kinds dropped). Rows: ticker (as FINRA
        writes it: ABRpD), cik and company (who held the ticker that settlement day), type, settlement_date,
        short_interest, avg_daily_volume, days_to_cover (999.99 is FINRA's cap), counts_from. sort short_interest |
        days_to_cover (largest first) | ticker."""
        return await run(service.short_interest_scan, settlement, day, at, min_shares, min_days_to_cover, kinds, sort,
                         output_name)

    @server.tool(annotations=writes_file)
    async def sector_scan(sic: list[str] | None = None, sic_words: list[str] | None = None,
                          exchange: list[str] | None = None, active: bool | None = None,
                          kinds: list[str] | None = None, output_name: str | None = None) -> dict:
        """Every listed company in an industry: SIC codes (["2834"], or ["283*"] for every code starting 283) OR
        words of the SIC description (["pharmaceutical"]: any word, any case), optionally on exchange (primary
        exchange: XNAS, XNYS, XASE, ARCX, BATS, "OTC Link") and active true/false. COMMON STOCK (CS, ADRC) by default;
        kinds ["all"] keeps warrants, units, preferreds. Rows: ticker, name, cik, sic, sic_description, exchange,
        list_date, type, active. SIC is the reference dump's LATEST (Massive ticker details), not as of a past day, and
        the dump has ticker details only for tickers active when it was taken: a delisted company is not here
        (sec_filings_scan's sic reads SEC's own code, delisted companies included)."""
        return await run(service.sector_scan, sic, sic_words, exchange, active, kinds, output_name)
