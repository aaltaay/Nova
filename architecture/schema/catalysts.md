# Data schema: Catalysts

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/catalysts/, research/catalysts/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Catalysts (ADR 024)

One pure classifier, `backend/catalysts/classify.py` (rules and `CATALYST_RULES_VERSION` in
`constants_catalysts.py`), for the backfilled history and the live desk. An item is
`catalyst` (`strength: "strong" | "weak"`), `negative` (dilution, delisting), `routine` or
`noise` (movers lists, "why is it moving", law-firm adverts, opinion, stock screens, roundups of
more than three tickers). Rules v6: a one-ticker "why is it moving" rewrite is labelled by the
cause its summary names ("... after the company priced a $5 million offering") when that cause
is a placed catalyst or dilution, and stays noise otherwise (no cause, "no news", a peer's news,
a denial, a list of stocks, an analyst piece). Rules v7 (#517): an EDGAR item of form `4` is a
Form 4 open-market purchase (transaction code `P`) by an officer or a director, its dollar total
stamped in `sec_items` as `P:<whole dollars>` (`catalysts/form4.py`); at or above
`CATALYST_INSIDER_BUY_MIN_USD` (25,000) it is `catalyst` / `listing_financing` / `weak`, below it
(or unstamped) `routine` / `corporate_routine`. Rules v8 (2026-10-02, AMOD): a raise (an offering, a
private placement, a `PIPE`) whose money or consideration is a digital-asset treasury ("bitcoin-funded",
"consisting of 3,170 bitcoin", never bitcoin mining) is `catalyst` / `crypto_treasury` / `weak` with
`dilution: true`, judged after the strong classes and before plain dilution (an EDGAR filing is searched
across its whole stored item text); `PIPE` (case-sensitive) is a raise word, except a headline about a PIPE's
investors or shares; an item's `n_tickers` counts names, not symbols (`classify.ticker_count`: `IONQ.WS`
names IONQ again, and one crypto pair on a company's story names the coin it is about -- AMOD + BTCUSD is
one -- while several pairs each count). A **verdict** for a symbol-day reads only
items published after the prior
session's 16:00 ET close and at or before its cutoff: `{verdict: "catalyst" | "negative" |
"routine_only" | "noise_only" | "none_found" | "not_checked", category, strength, title,
source, published_ts, url, negative_too, rules_version}` (plus `sources_answered`, `n_items`).
`none_found` only when a source looked; `not_checked` when none did. The live verdict adds
`news_pending: boolean` (a Nasdaq T1 / T12 halt inside the window with no resumption yet),
`halt_code: string | null` and `prior_session: {kind: "catalyst" | "negative", category, strength,
dilution, title, source, published_ts, url} | null` -- the best-ranked catalyst or negative item the
live catalyst feed recorded from the prior session's 04:00 ET open to its 16:00 close (ADR 024
amendment 2026-10-02). It is shown, never counted: `verdict`, `category`, `negative_too`,
`sources_answered` and the News pillar read only the window. `null` is none on file, never a claim the
company said nothing, and always `null` in Sim playback. The feed keeps its items in memory back to that
04:00 open (`CATALYST_FEED_MEMORY_HOURS` at least).

The setup board's `pillars.catalyst` is that verdict at arm time (`catalysts/live.py`:
Alpaca since the prior close, fetched in the background, Finnhub company news since the prior
close (`catalysts/live_finnhub.py`, paced at `CATALYST_FINNHUB_CALLS_PER_MIN` inside the free
tier's shared budget; its Benzinga copies dropped -- Finnhub stamps them four hours early, #516;
`sources_answered` names `finnhub` while a read younger than `CATALYST_FINNHUB_TTL_SEC` covers
the window), plus the live catalyst feed; `null`
when no source looked and nothing was found); `pillars.news` is `true` only for a classified
catalyst, `null` when unknown (nothing read, `news_pending`, or only an unplaced
`company_news` headline) and `false` otherwise; `pillars.headline` is the catalyst's headline
(it was a timestamp). The leaderboard's `has_news` keeps its meaning (an article exists).

**The verdict on the desk** (ADR 024 amendment, operator report 2026-09-23): every scanner row
(REST and `/ws/scanner`, through `scanner_surface.surface_rows`) carries `catalyst: verdict |
null` -- the live verdict as `{verdict, category, strength, title, source, published_ts, url,
negative_too, rules_version, sources_answered, n_items, news_pending, halt_code}`
(`catalysts/live.WIRE_KEYS`), `null` while no source has read the symbol (unknown, never "no
news"). Owner `catalysts/board.py`: an in-memory map recomputed off the loop every
`CATALYST_BOARD_INTERVAL_SEC` for the current rosters and stamped at read time. `has_news` /
`newest_headline_at` stay on the row with their old meaning. The News column, the "Has news"
chip (company news: a catalyst, dilution / a reverse split, or a halt for news; unread rows
kept), the Trader tab's chip, the HOD strip's flame and `/api/strategy/*`'s catalyst pillar and
score read `catalyst` when the row has it; a row without the key keeps the headline flame.
`GET /api/catalysts/{symbol}` (owner `catalysts/routes.py`, read-only; reads Alpaca and Finnhub
for the symbol first when a read is missing or stale; one release carried by several sources is
listed once, from the best-ranked source) answers the Trader's News panel: `{schema_version:
1, symbol, generated_at, window_start, verdict: verdict | null, items: [{item_id, source,
publisher, published_ts, title, url, kind: "catalyst" | "negative" | "routine" | "noise",
category, strength, dilution}], items_total}` -- items since the prior close, newest first, at
most `CATALYST_PANEL_MAX_ITEMS`.

**The live catalyst feed** (`backend/catalysts/feed.py`, always on; `NOVA_CATALYST_FEED=0`
off; ADR 024 amendment) records SEC EDGAR's latest filings, GlobeNewswire, PR Newswire,
Newsfile and FDA into `catalyst_feed.sqlite3` under `NOVA_CATALYST_DIR`, else
`F:\Nova\catalysts` when F: is mounted, else `<cache>/catalysts` (owner
`catalysts/feed_store.py`; `PRAGMA user_version = 1`, unknown versions refuse): `items` and
`item_tickers` in the research store's shape, and `coverage (source, start_ts, end_ts)` --
unbroken reading of a source, extended only when a poll reached back to the previous one. A
feed source counts in `sources_answered` only where a span covers the whole window.
**Form 4** (#517) is its own feed source, `edgar_form4` (owner `catalysts/feed_form4.py`): EDGAR's
latest Form 4s (`owner=only`), the issuer's entry only (its CIK names the ticker), each listed
issuer's filing read once as its full submission text; only an officer's or a director's
open-market purchase is recorded -- an `items` row with `source: "edgar"`, `form: "4"`, the stamp in
`sec_items` and a title like `Form 4: open-market purchase by <owner> (<role>), <shares> shares
($<value>)`. Its span is separate from `edgar`'s, so a Form 4 burst never breaks the 8-K / 6-K
span; a filing that cannot be read (after `CATALYST_FEED_FORM4_MAX_ATTEMPTS`, or unparseable) breaks
it there. It is not in `CATALYST_FEED_COVERAGE_SOURCES`: it reads one filing type, so its silence
never supports `none_found`.
`/api/diagnostics` adds the `catalyst_feed` row (group `recorder`) with
`evidence.sources: {name: {last_ok, last_error, items, gaps, covering_since}}` and
`evidence.finnhub: {enabled, pending, symbols, last_ok, last_error, reads}` (the Finnhub reader).

The research store `F:\Nova\catalysts\catalysts.sqlite3` (`NOVA_CATALYST_DIR`; `PRAGMA
user_version = 1`, unknown versions refuse; owner `research/catalysts/`, never read by the
backend) holds `targets (ticker, session_date, window_start, cutoff, window_end, origin)`,
`items (item_id "<source>:<id>", source edgar | alpaca | finnhub | massive, published_ts,
title, summary, url, publisher, n_tickers, form, sec_items, fetched_ts)`, `item_tickers`,
`checks (ticker, session_date, source, status ok | error | unavailable | out_of_range,
n_items, detail, checked_ts)` and `verdicts` per rules version. An `edgar` item's
`published_ts` is its EDGAR acceptance time with each bulk-JSON row read on its own clock: SEC
writes a `Z` on every `acceptanceDateTime`, but some filers' JSON holds Eastern wall time behind
it (`research/catalysts/edgar_clock.py`; ADR 024 amendment 2026-09-30). SEC's bulk
`submissions.zip` and `companyfacts.zip` are kept beside it under `edgar/`, Nasdaq's halt
pages under `halts/raw/`. Nasdaq's halt history (2021-10 on) is loaded into the leaderboard's
`halt_events` (source `nasdaq_trade_halt_rss`) by `research/catalysts/backfill_halts.py`, and
its checks and labelled items into the leaderboard's `catalyst_checks` / `catalyst_items` by
`research/catalysts/export_leaderboard.py` (#498), so Sim playback of a past day shows each
mover's verdict at the playhead ("Catalysts in playback" under Scanner leaderboard).

