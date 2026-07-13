---
title: Scanner Data Provider Decision (IBKR primary vs Alpaca SIP)
date: 2026-07-13
status: decided-direction
---

# Scanner Data Provider — IBKR primary (no Alpaca SIP)

## Decision

**Do not buy Alpaca Algo Trader Plus ($99 SIP).**  
**Primary live discovery → Interactive Brokers market scanners + L1 subscriptions.**  
**Keep existing Alpaca codepaths intact behind a provider flag for undo / hybrid.**  
**Keep free Alpaca (or equivalent) only for non-SIP needs: news headlines, optional fallback.**

## Why (strategy-grounded)

Warrior Trading Scanning 101 + Strategies Ch.3/7 (Pinecone + Obsidian):

1. Morning workflow is **Top Gainer / Top Gapper list scanners**, not a custom full-universe poll.
2. Those scanners already search the whole market and return a short list (~40–60 names meeting ≥5% etc.).
3. Ross then focuses on the **top 3–4 leading gainers** after checking % gain, price, float, RVOL, news freshness, charts, L2.
4. Gap and Go stock finding = **Gap Scanner** → Five Pillars → charts → Level 2 entry.

Nova only needs the **top of a universe-wide ranked list**, not 200 custom gapper rows. IBKR `reqScannerSubscription` (≤50 results, server-side universe search) matches that model.

## What each vendor is for

| Job | Provider | Notes |
|-----|----------|-------|
| Live top gappers / gainers / most active | **IBKR scanner** | Requires L1 Networks A/B/C or Equity Add-On |
| Quotes on the shortlist | **IBKR L1** | Uses market-data lines (~50 is fine) |
| Level 2 + orders | **IBKR** | Already in Nova |
| News flame / catalyst headlines | **Alpaca free news** (keep) | Does **not** require SIP |
| Float / mkt cap / short interest | **yfinance** (already) | Not Alpaca |
| Full-universe custom gap% over ~4k symbols | Alpaca SIP | **Reject** — strategy doesn't need it; costs $99 |
| Free IEX as live scanner | Alpaca Basic | **Reject for live** — thin tape, misses movers |

## Soft-toggle (do not destroy Alpaca)

When implementing, add constants (defaults keep current behavior until flipped):

```
DISCOVERY_PROVIDER = "alpaca" | "ibkr" | "hybrid"   # default alpaca until IBKR path proven
MOVER_PROVIDER     = "alpaca" | "ibkr"
NEWS_PROVIDER      = "alpaca"                       # only implemented source today
QUOTE_STREAM_PROVIDER = "alpaca" | "ibkr"
```

- Extract Alpaca discovery/stream into `providers/alpaca/` without behavior change first.
- Add `providers/ibkr/scanner.py` that normalizes IBKR scanner rows into the existing gapper/mover cache shape.
- Flip `DISCOVERY_PROVIDER=ibkr` only after side-by-side validation.
- Alpaca modules stay importable so rollback is a constant change, not a rewrite.

## IBKR subscriptions required for this path

1. **L1 streaming:** NYSE A + Network B + NASDAQ C (~$4.50) **or** Snapshot Bundle + Equity/Options Add-On.
2. **L2 (small-cap depth):** NASDAQ TotalView-OpenView (~$16.50); OpenBook optional for NYSE names.
3. Gateway running; `IBKR_ENABLED=true`.

## Risks / gaps to validate before flipping the flag

1. Premarket: confirm IBKR scan codes cover premarket % vs prior close (gapper) vs all-day gainer.
2. Data-line budget: ~50 L1 symbols + 3 L2 must fit account allotment (boosters if not).
3. API/off-platform: some depth packages need EDS for non-TWS API — verify TotalView works via Gateway/`ib_async`.
4. News remains Alpaca-free; if Alpaca news ever requires paid data, replace news provider separately.
5. HOD Momo today listens to a broad Alpaca WS universe — under IBKR it must shrink to scanner shortlist + watched symbols (acceptable for Ross-style focus).

## Undo

Set providers back to `alpaca`. No deletion of Alpaca scan/WS/news code in the transition PR.

## Related

- Course: BA101 Ch.12 Scanning 101; SS101 Ch.3 / Ch.7 Gap and Go
- Nova: `Automation-Strategy-Backbone.md`, IBKR module CHANGELOG 2026-07-10
- Alpaca SIP pricing: Algo Trader Plus ~$99/mo — explicitly out of scope
