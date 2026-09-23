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
