"""One-off harness: time IBKR Top Gainers/Losers scanner work.

Does NOT modify production code. Uses a separate Gateway clientId so it
does not steal the Nova API connection (default clientId 17).

Usage (from repo root):
  py -3 tools/_bench_ibkr_gainers_scan.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
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

from ib_async import IB, ScannerSubscription, Stock  # noqa: E402

HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
PORT = int(os.environ.get("IBKR_LIVE_PORT", "4001"))
# Ephemeral bench id — avoid colliding with Nova's IBKR_CLIENT_ID (usually 17).
CLIENT_ID = int(os.environ.get("NOVA_BENCH_CLIENT_ID", "91"))
ABOVE_PRICE = float(os.environ.get("BLAST_MIN_PRICE", "0.5"))
MAX_ROWS = 50
ROUNDS = 3
SCAN_TIMEOUT = 25.0
QUALIFY_TIMEOUT = 15.0
SNAPSHOT_TIMEOUT = 20.0


async def time_scanner(ib: IB, scan_code: str) -> tuple[float, int, list[str]]:
    sub = ScannerSubscription(
        numberOfRows=MAX_ROWS,
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode=scan_code,
        abovePrice=ABOVE_PRICE,
    )
    t0 = time.perf_counter()
    rows = await asyncio.wait_for(ib.reqScannerDataAsync(sub), timeout=SCAN_TIMEOUT)
    elapsed = time.perf_counter() - t0
    symbols = []
    seen = set()
    for row in rows:
        try:
            sym = row.contractDetails.contract.symbol
        except AttributeError:
            continue
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    return elapsed, len(symbols), symbols


async def time_snapshots(ib: IB, symbols: list[str]) -> tuple[float, int]:
    if not symbols:
        return 0.0, 0
    contracts = [Stock(s, "SMART", "USD") for s in symbols]
    t0 = time.perf_counter()
    qualified = await asyncio.wait_for(
        ib.qualifyContractsAsync(*contracts), timeout=QUALIFY_TIMEOUT,
    )
    qualified = [c for c in qualified if c is not None]
    tickers = await asyncio.wait_for(
        ib.reqTickersAsync(*qualified), timeout=SNAPSHOT_TIMEOUT,
    )
    elapsed = time.perf_counter() - t0
    ok = sum(1 for t in tickers if t is not None)
    return elapsed, ok


def row(label: str, seconds: float, extra: str = "") -> str:
    return f"  {label:<42} {seconds:7.2f}s{extra}"


async def main() -> int:
    ib = IB()
    print(f"Connecting {HOST}:{PORT} clientId={CLIENT_ID} ...")
    await ib.connectAsync(HOST, PORT, clientId=CLIENT_ID, timeout=10)
    if not ib.isConnected():
        print("FAIL: not connected")
        return 1
    print("Connected. Running timing rounds (production code untouched).\n")
    # Avoid Windows console encoding issues on any later unicode.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results: list[dict] = []
    for i in range(1, ROUNDS + 1):
        print(f"-- Round {i}/{ROUNDS} --")
        g_scan_s, g_n, g_syms = await time_scanner(ib, "TOP_PERC_GAIN")
        print(row("TOP_PERC_GAIN scanner only", g_scan_s, f"  -> {g_n} symbols"))

        l_scan_s, l_n, l_syms = await time_scanner(ib, "TOP_PERC_LOSE")
        print(row("TOP_PERC_LOSE scanner only", l_scan_s, f"  -> {l_n} symbols"))

        g_snap_s, g_ok = await time_snapshots(ib, g_syms)
        print(row("Gainers snapshot_quotes (batch)", g_snap_s, f"  -> {g_ok}/{g_n} quotes"))

        l_snap_s, l_ok = await time_snapshots(ib, l_syms)
        print(row("Losers snapshot_quotes (batch)", l_snap_s, f"  -> {l_ok}/{l_n} quotes"))

        g_full = g_scan_s + g_snap_s
        l_full = l_scan_s + l_snap_s
        both = g_full + l_full
        print(row("get_gainers equivalent (scan+snap)", g_full))
        print(row("get_losers equivalent (scan+snap)", l_full))
        print(row("run_gainers_update-like (both)", both))
        print()
        results.append({
            "g_scan": g_scan_s,
            "l_scan": l_scan_s,
            "g_snap": g_snap_s,
            "l_snap": l_snap_s,
            "g_full": g_full,
            "l_full": l_full,
            "both": both,
        })
        if i < ROUNDS:
            await asyncio.sleep(2)

    def avg(key: str) -> float:
        return sum(r[key] for r in results) / len(results)

    def mx(key: str) -> float:
        return max(r[key] for r in results)

    print("== Summary (avg / max over rounds) ==")
    for label, key in [
        ("TOP_PERC_GAIN scanner", "g_scan"),
        ("TOP_PERC_LOSE scanner", "l_scan"),
        ("Gainers snapshots", "g_snap"),
        ("Losers snapshots", "l_snap"),
        ("get_gainers equivalent", "g_full"),
        ("get_losers equivalent", "l_full"),
        ("Full movers update (g+l)", "both"),
    ]:
        print(f"  {label:<42} avg={avg(key):6.2f}s  max={mx(key):6.2f}s")

    both_avg = avg("both")
    print()
    if both_avg > 20:
        print(
            f"Verdict hint: full cycle avg {both_avg:.1f}s > 20s interval "
            "-> cutting to 10s likely piles up."
        )
    elif both_avg > 10:
        print(
            f"Verdict hint: full cycle avg {both_avg:.1f}s is between 10-20s "
            "-> 10s interval is tight; 15s safer."
        )
    else:
        print(
            f"Verdict hint: full cycle avg {both_avg:.1f}s < 10s "
            "-> 10s interval looks feasible from timing alone."
        )

    ib.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
