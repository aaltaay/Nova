# ADR 040 -- The Cryptos page: a reference board for the 24/7 market, and the stocks it moves

**Status:** Accepted · **Date:** 2026-09-30
**Builds on:** [[005-frontend-feature-slices]] · [[010-ib-loop-isolation]] · [[012-local-first-chart-bars]] (the paced
historical service) · [[024-catalyst-classifier]] (Alpaca news, a rules read) · [[028-why-its-moving]] (checks with a
source, unknown is unknown)
**Decided by:** the operator, 2026-09-30 ("give us a new tab called Cryptos and create a dashboard showing what a person
needs to see in the crypto world"; mockup v1 approved: "i love the demo. go ahead and build exact replica plz! ... when the
user hover over things, make sure you show in friendly visual way what does it mean")

## Context

Nova trades US stocks through IBKR and nothing else. The operator asked how hard crypto would be: spot crypto needs its
own contract type, decimal quantities, 24/7 clock rules and a different fee schedule, and nothing on the desk showed the
crypto market at all. The approved mockup is a single page: market tiles, a coins table, a chart, a 24/7 clock, the
stocks that move with crypto (the part Nova can trade today), leverage, money flows, and what comes next.

IBKR has none of most of it. Its crypto venues (Paxos, Zero Hash) list a handful of coins and carry no market caps,
funding rates, open interest, ETF flows or sentiment, and the operator's account may not have crypto permission at all.

## Decision

1. **A new shell page, `Cryptos`, in the nav rail** (`frontend/src/cryptos/`, backend `backend/crypto/`), laid out as
   the approved mockup. Read-only: nothing on it places, stages or cancels an order, and nothing on it feeds a scanner
   row, a stock's chart, HOD Momo, a setup lane or a bot.
2. **Crypto numbers come from named public reference sources, each shown with its name** -- a carve-out from the single
   market-data feed rule (rule 13 of `.cursor/rules/single-market-data-feed.mdc`), like the Earnings calendar and Nova
   News: CoinGecko (prices, 1h / 24h / 7d changes, volumes, market caps, dominance, 7-day paths), Coinbase Exchange
   (candles for the chart and the price at each 16:00 ET close), alternative.me (Fear & Greed), Hyperliquid (perpetual
   funding and open interest), DefiLlama (stablecoin supply), Deribit (options open interest by expiry), Alpaca (crypto
   news, read by `crypto/classify.py`). All keyless; `COINGECKO_DEMO_API_KEY` optionally raises CoinGecko's rate limit.
   A source that fails says why on the page, and its numbers read unknown -- never another source's numbers in their
   place.
3. **Stock numbers on the page are IBKR's.** The "Crypto -> stocks you can trade" panel reads the bridge stocks (IBIT,
   ETHA, MSTR, COIN, MARA, RIOT, CLSK, HOOD) through the existing cold `snapshot_quotes` path and their regular-hours
   daily closes through the paced historical service (`historical_service.request_rth_daily_closes`, background
   priority: shed while a chart is loading or the pacing budget is tight). The "Spot" chip asks IBKR whether it lists
   the coin (`Crypto(sym, 'PAXOS' | 'ZEROHASH', 'USD')`, once per process). Nova still cannot place a crypto order; the
   chip says where the coin can be bought, not that Nova buys it.
4. **Implied moves are arithmetic on real numbers, labelled as a hint.** A stock's beta is the least-squares slope of
   its daily regular-hours close-to-close returns on BTC's (ETH's for ETHA) 16:00 ET-to-16:00 ET returns over the last
   `CRYPTO_BETA_DAYS` sessions (at least `CRYPTO_BETA_MIN_DAYS`, else unknown). Implied = the coin's move since the last
   16:00 ET close x beta; "ahead" / "behind" when the stock's own move since that close differs by more than
   `CRYPTO_BRIDGE_READ_BAND_PT` points. BTC's 30-day correlation to the Nasdaq 100 uses QQQ's closes the same way.
5. **Nothing polls while nobody looks.** The page's reads mark the board wanted; two background threads (web sources,
   IBKR) refresh each source on its own cadence while it is wanted within `CRYPTO_WANTED_SEC`, and stop otherwise. A
   route never waits on the network: it answers what is cached, with `loading` until each source has answered once.
   `NOVA_CRYPTO=0` turns the refreshers off.
6. **What has no free source is a stated absence:** 24-hour liquidations, daily spot ETF flows, a macro calendar and
   token unlocks. The tiles and panels keep their place and say so; the money-flow chart shows daily stablecoin supply
   change until an ETF source exists.
7. **Every number explains itself.** Hovering any tile, cell, chip, level or lane opens a card with what it means in
   plain words, a small drawing (a scale with the reading on it, a split bar, the formula with today's numbers, the
   session ribbon), what it reads now and why a trader cares. The words live in one glossary
   (`frontend/src/cryptos/tips/glossary.ts`) so they stay consistent.
8. **The sample desk shows the approved mockup's figures**, marked as sample data like the rest of that desk, and reads
   nothing live.

## Consequences

- Two prices for one coin can differ by a few dollars: the table's is CoinGecko's cross-exchange average, the chart's
  is Coinbase's last trade. Each is labelled.
- Funding and open interest are one venue's (Hyperliquid, keyless and reachable from the US). The big offshore
  exchanges are geo-blocked from the operator's desk, so aggregate figures would need a paid source.
- Public APIs rate-limit. The cadences keep CoinGecko near two calls a minute while the page is open, and none when it
  is not.
- The page reads the live market on every venue; on a Sim replay desk it says so rather than pretending to follow the
  replay.
- Not in v1: trading crypto in Nova (a separate, larger build), crypto alerts, crypto on the watch list, per-coin
  detail pages.

Rejected: IBKR crypto quotes for the table (a handful of coins, and none without crypto permission); scraping HTML for ETF
flows (Farside sits behind a bot wall, and scraping is a desk anti-pattern); a paid aggregate (Coinglass) before the
operator chooses to pay; guessing the missing numbers; a model writing the explanations (the rules and the glossary
cost no tokens).
