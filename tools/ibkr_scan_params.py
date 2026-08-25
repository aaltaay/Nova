"""One-off harness: confirm which IBKR scan code works for a "Large Cap"
swing table before wiring any production code (see plan Step 0).

Does NOT modify production code. Uses a separate Gateway clientId so it
does not steal the Nova API connection (default clientId 17).

What it checks, for each candidate scan code:
  1. Baseline run (no marketCapAbove) -> symbols returned.
  2. Filtered run with marketCapAbove + aboveVolume + stockTypeFilter=CORP
     -> symbols returned.
  3. Whether the filtered run actually shrank/changed the roster to
     large, liquid names (a scan code that ignores marketCapAbove will
     return the same rows in both runs).

Gotchas found and fixed here (see PROBLEM_LOG.md 2026-08-25):
  - ScannerSubscription.marketCapAbove is in MILLIONS of USD (IB's raw
    reqScannerParameters XML documents the wire code as
    "marketCapAbove1e6" with suffix "*1,000,000"). $50B floor = 50_000,
    not 50_000_000_000.
  - aboveVolume is a raw share count IntField -- no scaling.
  - stockTypeFilter must be the plain value "CORP" (not the XML-internal
    label "inc:CORP") to exclude ETFs/ETNs/REITs/CEFs. instrument="STK"
    alone does NOT exclude ETFs -- they are STK-typed contracts in IB's
    model.

Usage (from repo root):
  py -3 tools/ibkr_scan_params.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Load .env if present (no secrets printed).
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from ib_async import IB, ScannerSubscription  # noqa: E402

HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
PORT = int(os.environ.get("IBKR_LIVE_PORT", "4001"))
# Ephemeral diagnostic id -- avoid colliding with Nova's IBKR_CLIENT_ID (usually 17)
# and the _bench_ibkr_gainers_scan.py convention (91).
CLIENT_ID = int(os.environ.get("NOVA_DIAG_CLIENT_ID", "95"))
MAX_ROWS = 50
SCAN_TIMEOUT = 25.0

# IB's raw scanner XML documents MKTCAP's field code as "marketCapAbove1e6"
# with suffix "*1,000,000" -- ScannerSubscription.marketCapAbove is in
# MILLIONS of dollars, not raw dollars. $50B floor = 50_000.
MARKET_CAP_ABOVE_MILLIONS = float(os.environ.get("DIAG_MARKET_CAP_ABOVE_MM", "50000"))  # $50B
ABOVE_VOLUME = int(os.environ.get("DIAG_ABOVE_VOLUME", "1000000"))  # raw shares (IntField, no scaling)
ABOVE_PRICE = float(os.environ.get("DIAG_ABOVE_PRICE", "20"))

CANDIDATE_SCAN_CODES = [
    "HOT_BY_VOLUME",
    "TOP_VOLUME_RATE",
    "MOST_ACTIVE",
    "TOP_PERC_GAIN",
    "TOP_PERC_LOSE",
]


async def run_scan(ib: IB, scan_code: str, *, with_cap_filter: bool) -> list[str]:
    kwargs = dict(
        numberOfRows=MAX_ROWS,
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode=scan_code,
        abovePrice=ABOVE_PRICE,
    )
    if with_cap_filter:
        kwargs["marketCapAbove"] = MARKET_CAP_ABOVE_MILLIONS
        kwargs["aboveVolume"] = ABOVE_VOLUME
        kwargs["stockTypeFilter"] = "CORP"  # exclude ETF/ETN/REIT/CEF pollution
    sub = ScannerSubscription(**kwargs)
    try:
        rows = await asyncio.wait_for(ib.reqScannerDataAsync(sub), timeout=SCAN_TIMEOUT)
    except asyncio.TimeoutError:
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for r in rows:
        try:
            sym = r.contractDetails.contract.symbol
        except AttributeError:
            continue
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    return symbols


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ib = IB()
    print(f"Connecting {HOST}:{PORT} clientId={CLIENT_ID} ...")
    await ib.connectAsync(HOST, PORT, clientId=CLIENT_ID, timeout=10)
    if not ib.isConnected():
        print("FAIL: not connected")
        return 1
    print("Connected. Production code untouched.\n")

    print(f"Filter under test: marketCapAbove={MARKET_CAP_ABOVE_MILLIONS:,.0f}mm "
          f"(=${MARKET_CAP_ABOVE_MILLIONS / 1000:,.1f}B) "
          f"aboveVolume={ABOVE_VOLUME:,} abovePrice={ABOVE_PRICE}\n")

    verdicts: dict[str, str] = {}
    for code in CANDIDATE_SCAN_CODES:
        print(f"== {code} ==")
        baseline = await run_scan(ib, code, with_cap_filter=False)
        filtered = await run_scan(ib, code, with_cap_filter=True)
        print(f"  baseline  ({len(baseline):2d}): {baseline[:15]}")
        print(f"  filtered  ({len(filtered):2d}): {filtered[:15]}")

        if not baseline and not filtered:
            verdict = "NO DATA (empty on both runs -- code may be invalid/unsubscribed)"
        elif baseline == filtered:
            verdict = "IGNORES marketCapAbove (identical rosters) -- reject"
        elif not filtered:
            verdict = "filtered run empty -- cap filter accepted but no matches at this floor"
        else:
            baseline_set = set(baseline)
            filtered_set = set(filtered)
            shrank = filtered_set.issubset(baseline_set) or len(filtered_set - baseline_set) < len(filtered_set)
            verdict = (
                "RESPECTS marketCapAbove (roster changed) -- candidate"
                if filtered_set != baseline_set
                else "unclear"
            )
        print(f"  verdict: {verdict}\n")
        verdicts[code] = verdict
        await asyncio.sleep(1)

    print("== Summary ==")
    for code, v in verdicts.items():
        print(f"  {code:<18} {v}")

    ib.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
