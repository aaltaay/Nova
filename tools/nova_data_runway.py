"""The cash-runway tool of the nova-data MCP server (ADR 059, #1102): a company's cash, operating cash burn, runway,
share-count growth and shelf / offering filings as known on a past day.

Split from ``tools/nova_data_mcp.py`` along the tool-set seam, like ``nova_data_research.py``: ``RunwayTools`` is the
body (``cash_runway``), ``register`` its MCP description. The method is ``research/market_reads/runway.py`` and its
answer shape ``architecture/schema/agent-desk.md`` ("The data front door over MCP"). Read-only on the data.
"""
from __future__ import annotations

from typing import Any

PRELOAD = ("market_reads.runway",)
DEFAULT_LOOKBACK_DAYS = 1095        # == market_reads.runway.DEFAULT_LOOKBACK_DAYS (a test holds the two together)


class RunwayTools:
    """Tool bodies; the host class gives ``json_safe`` (``nova_data_mcp._json_safe``)."""

    def cash_runway(self, symbol: str, day: str, cik: str | None = None,
                    lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
        from market_reads import runway
        return {"ok": True, **self.json_safe(runway.runway(symbol, day, cik, lookback_days))}


def register(server, service, run, reads, writes_file) -> None:
    """The tool on ``server`` (``run`` executes a body off the event loop; heavy ones one at a time)."""

    @server.tool(annotations=reads)
    async def cash_runway(symbol: str, day: str, cik: str | None = None,
                          lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
        """A company's cash runway and dilution filings as known on a past day (YYYY-MM-DD; no look-ahead): the
        newest balance sheet's cash and short-term investments, the newest quarterly operating cash flow (burn),
        runway in months (null unless the cash and the burn are from one quarter and cash is being used), shares
        outstanding growth over 4 and 8 quarters, and the S-1 / S-3 / F-1 / F-3 / 424B1-5 / 8-K filings in the
        lookback_days before the day (1-3650, default 1095) with their dates. Every figure names its statement's
        period_end and filing_date; unknown is null, never 0. Massive dates a period by the newest filing that carried
        it, so the newest statement known on a past day is often over a year old: read age_days / stale / notes. A
        filing is not an offering that closed. A reused ticker reads the company that held it that day (cik picks one)."""
        return await run(service.cash_runway, symbol, day, cik, lookback_days)
