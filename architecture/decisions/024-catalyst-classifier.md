# ADR 024 -- Catalysts: one classifier for the history and the live desk

**Status:** Accepted · **Date:** 2026-09-23
**Builds on:** [[022-setup-scanner-tape-gate]] · [[023-scanner-leaderboard]]

## Context

The Five Pillars' news pillar was "any article". An audit of the rebuilt leaderboard
(2026-09-22) found it meant almost nothing:

- The research catalyst (`research/orb/select_gng.py`) counted any Massive article tagged
  with the ticker. Of 2,243 top-10 movers over 66 days, 95% had no article at all in that
  archive and, of those that did, a fifth were movers lists, "why is it moving" pieces and
  law-firm adverts. The archive has no PR Newswire, Business Wire or Accesswire -- the wires
  small caps announce on.
- The live pillar (`setup_scanner/grade.py`) passed on any non-listicle Alpaca article today,
  law-firm adverts included, and its `headline` field held a timestamp.

The operator asked for data kept on the drive, from sources that name a real catalyst.

## Decision

1. **One pure classifier**, `backend/catalysts/classify.py` with its rules in
   `constants_catalysts.py` (`CATALYST_RULES_VERSION`). It labels an item `catalyst`
   (`strong` / `weak`, by class), `negative` (dilution, delisting), `routine` or `noise`,
   and answers a symbol-day with a **verdict** from the items published after the prior
   session's 16:00 ET close and at or before a cutoff -- never later.
2. **`none_found` needs a source that looked.** A source that cannot reach a date
   (`out_of_range`) or has no id for the ticker (`unavailable`) did not look; with no source
   answering the verdict is `not_checked`. "No catalyst" is a trait to test, not missing data.
3. **The history is backfilled onto F:** (`research/catalysts/`, store
   `F:\Nova\catalysts\catalysts.sqlite3`, `PRAGMA user_version = 1`, unknown versions refuse)
   from four free sources: SEC EDGAR (the bulk `submissions.zip` kept on F:, and the EX-99
   press release of every 8-K / 6-K inside a window), Alpaca (Benzinga's newsroom), Finnhub's
   free tier (one year) and the Massive archive already on F:. Research only; nothing in
   `backend/` imports it.
4. **The live desk uses the same classifier and window.** `catalysts/live.py` fetches a
   symbol's Alpaca articles since the prior close in the background; the setup scanner's
   News pillar passes only on a `catalyst` verdict, and is `null` (unknown, never failed)
   when no fetch covers the moment -- a replay playhead on another day included.
5. The scanner's News flame (`scanner_news_badge`) and the leaderboard's `has_news` are
   unchanged: they say an article exists, not that it is a catalyst.

## Consequences

- A grade `A` now needs a real catalyst; grades are lower than before by design.
- Research can split any setup by catalyst class with the rules the desk trades on.
- Live coverage is Alpaca only; EDGAR's live filings feed and the wire RSS feeds are the next
  sources (recorded forward, like the leaderboard). The backfill measures what they would add.
- Rules change by bumping `CATALYST_RULES_VERSION`; verdicts are stored per version, and a
  hand-labelled sample (`research/catalysts/labels.py`) measures each version.

## Amendment 2026-09-23 -- the primary sources live, halts, and the pillar's unknowns

The operator asked for the primary sources, not only an aggregator: SEC EDGAR, the press-release
wires, Nasdaq halts and FDA.

1. **A live catalyst feed** (`backend/catalysts/feed.py`, always on, `NOVA_CATALYST_FEED=0` turns
   it off) records SEC EDGAR's latest filings (8-K, 6-K, 424B, S-1, S-3, F-1, F-3, SC TO-T; an
   8-K / 6-K read for its press release by the shared `catalysts/sec_text.py`), GlobeNewswire,
   PR Newswire, Newsfile's small-cap industry feeds and FDA press announcements into
   `catalyst_feed.sqlite3` beside the research store (owner `catalysts/feed_store.py`,
   `PRAGMA user_version = 1`). Business Wire and Accesswire publish no free all-news feed Nova
   can read; they reach the desk only through Benzinga (Alpaca) and the EDGAR copy.
2. **Coverage is proven.** A poll extends its source's span only when its oldest item is no newer
   than the previous poll; a burst larger than the page, an error or a stopped process breaks it.
   The live verdict lists a feed source in `sources_answered` only when an unbroken span covers
   the whole window -- so "none found" is never claimed across a gap.
3. **News pending.** A Nasdaq T1 / T12 halt inside the window with no resumption yet sets
   `news_pending` on the verdict; the News pillar is then unknown, not failed.
4. **The pillar's unknowns.** The verdict keeps an unplaced single-company headline as a weak
   catalyst (`company_news`) so the history stays one classifier, but the live News pillar treats
   it as unknown: on 800 labelled items it was right about half the time.
5. **Halt history.** Nasdaq Trader's halt page per date (2021-10 on) is loaded into the
   leaderboard's `halt_events` with the live desk's parser (`research/catalysts/backfill_halts.py`),
   so Sim playback of a rebuilt day shows its halts. The history shows a halt's final code: a news
   halt that opened T1 reads T3 once resolved.
6. **Research reference data** in `orb.duckdb`: `sec_shares` (shares outstanding as filed, from
   SEC's bulk `companyfacts.zip` on F:) and `short_interest` (FINRA, from the Massive dump), read
   with no hindsight by `split_trades.py`.

Rejected: scraping Business Wire / Accesswire newsroom pages (not an official feed; the halt-RSS
rule "official feed, never HTML scrape" applies) and company IR pages (they repeat the release the
wire and EDGAR already carry). FDA's feed names drugs, not tickers: it maps a release only when a
listed company's full name appears, so it adds no coverage claim.

## Amendment 2026-09-23 (evening) -- the verdict on the desk, rules v5

The operator opened the Gainers board and the Trader's News panel and found "garbage": the top
three gainers all showed the same Benzinga market wrap ("Dow Falls 100 Points; General Mills Posts
Upbeat Q1 Earnings", seven tickers named in passing), IPDN's panel read it as "moved price 90%",
and HCTI's real PR Newswire release (a letter of intent to buy a robotics business) showed nothing.
An audit of the top 15 found real company news on 5; the desk showed none of the 5, because the
verdict fed only the setup scanner and every other surface still read "an article exists".

1. **Decision 5 is reversed for the desk, kept for the record.** Every scanner row carries
   `catalyst` -- the verdict (`catalysts/live.compact`), `null` while unread -- stamped at read time
   from a map `catalysts/board.py` recomputes off the loop every `CATALYST_BOARD_INTERVAL_SEC`. The
   News column, the "Has news" chip, the Trader tab's chip, the HOD strip's flame and the Watchlist's
   Five Pillars / catalyst score read it. `has_news` keeps its meaning (an article exists) because
   the leaderboard records it and the research rebuilds compare against it; a row without
   `catalyst` (a played-back board, the Catalysts list, an older API) keeps the headline flame.
2. **The Trader's News panel reads the verdict** (`GET /api/catalysts/{symbol}`, polled): the
   catalyst, its source and age, what was checked, then every item read with its label, movers
   lists and wraps folded away. The rules-v1 impact read no longer leads the panel -- it judged the
   newest article, whatever it was; it stays on the Catalysts list.
3. **Rules v5** (`catalyst-rules-v5-2026-09-23`), measured against the 255,006 backfilled items:
   1,951 labels change. A "share consolidation" / "1-for-N" is a reverse split (negative);
   Benzinga circuit-breaker notices ("Shares Halted On Circuit Breaker", "Resume Trading") are halt
   notices, not company news (1,074 Alpaca items had been weak catalysts); `at-the-market` needs a
   word boundary ("Beat the Market" was an offering); debt elimination and named customer wins are
   positive; a Benzinga movers-section URL keeps an item only when a specific class places it.
   `sec_text.headline` joins a line cut on a connecting word ("... HCLP Debt and" / "Heppner Equity
   Interests"). Verdicts are stored per version; the research store needs a v5 re-run.

Rejected: filtering the Alpaca outlets harder (for these names Alpaca's feed is Benzinga lists and
wraps -- filtering it harder reaches "nothing", which the verdict already says with its sources);
dropping the movers-URL rule outright (588 of its items would have become "company news", mostly
halt notices and commentary); and turning an unplaced Regulation FD exhibit into company news (the
backfill showed slide-deck text, e.g. a photo credit, under 7.01).
