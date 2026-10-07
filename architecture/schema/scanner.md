# Data schema: Scanner rows, floats, the leaderboard and watchlist rows

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/scanner_surface.py, backend/leaderboard/, backend/strategy/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Scanner rows and HOD Momo alerts on the wire (QA batch, 2026-09-22)

The REST scanner routes and `/ws/scanner` (`roster_replace` and the connect
snapshot) serve rows through one pipeline, `scanner_surface.surface_rows`:
blocklisted symbols removed, listing `exchange` attached, reference columns
decorated, Large Cap scored -- a roster push can no longer bring back a
blocklisted ticker or drop `large_cap_score`. Each row may carry
`rvol_source: "yfinance" | "alpaca" | null`, naming the average daily volume
`rel_volume` divides by (null or absent when unreported; the desk then says
so rather than guessing). A price-patch row's existing
`quote_quality: "close_fallback"` means the price is IBKR's prior close with no
trade yet; the desk shows it as such and states no change.
`GET /api/scan/envelope` (owner `routes/scan.py`) answers `rev`, `mode`,
`health` (with `integrations`), `data_feed`, `feed_error: string | null` and
`tables: {gappers | gainers | losers | afterhours | large_cap: {table_state,
roster_ts, last_scan}}` -- never rows. A persistent-authoritative desk (ADR
008), whose rows follow `/ws/scanner`, polls it so mode, health and feed
errors do not freeze at mount.

No socket frame on `/ws/scanner` or `/ws/hod-momo` carries a bare `NaN` /
`Infinity`: a non-finite float is `null` (`scanner_wire.dumps_wire`,
`hod_momo_models.alert_to_dict`). A HOD Momo alert's `id` is
`"<created_ms>-<SYMBOL>-<strategy_id>"`, taken from when Nova raised it
(`created_ts`), so two alerts raised on one stale print never share an id;
`timestamp` stays the trigger print's time. `change_pct` is `number | null`
-- null when the snapshot had none, never an invented 0.0. The HOD debug
snapshots' `last_enriched` is epoch seconds (`time.time()`), `0` when never
enriched. Integration-health `detail` strings are ASCII.

QA pass two (2026-09-22, Scanner / header / layout batch): a cached scanner
row -- and so every REST reply -- carries `quote_quality: "close_fallback" |
null` once an L1 tick has touched it (`ibkr/l1_apply.py`): `close_fallback`
means the price is IBKR's prior close with no print yet, `null` states a
print; a row no tick has touched has no key. A name-only row's `volume` is
`null` until a quote carries one (never a placeholder `0`), and an L1 tick
without a volume leaves the row's volume as it was. The universe gapper
enrichment and the after-hours L1 reprice stamp `rvol_source: "alpaca"` on
the RVOL they divide by the Alpaca IEX average. A gapper / after-hours row
restored from a snapshot has `change_pct` / `change_abs` measured from its
price against the prior close (`null` when either is unknown) -- never its
gap. A HOD alert restored from disk (today's restore and
`/api/hod-momo/history/{date}`) created before `HOD_MOMO_INVENTED_CHANGE_BEFORE_TS`
with `change_pct` exactly `0` reads `change_pct: null` (the pre-fix fill-in);
the archive file is not rewritten. `/api/hod-momo/debug/symbol/{sym}` and
`DELETE /api/hod-momo/blocklist/{symbol}` accept a symbol with a slash
(`BRK/B`). `/api/strategy/*` grades the rows the Scanner shows
(`scanner_surface.surface_rows`: blocklist out, RVOL / float / news in), and a
move past +100% reaches the graders in percent so it is never read as a
fraction under 1.0. Bar-derived sensor readings (`vwap`, `macd`, `emas`,
`last-move`) add `data.bars_as_of` -- epoch seconds of the newest 1-minute bar
they were computed from, `null` without bars -- so the board can say a
reading is stale.

**The gap is never yesterday's** (operator report, 2026-09-24: GCTK read
+9.9% on the Focus rail all premarket while it traded +103% on its prior
close). IBKR's open tick (14) names the previous session's open until the
regular session opens, so it counts as today's open only from 09:30 ET on an
exchange day (`ibkr/open_tick.py`, for the streaming line and
`snapshot_quotes`). Before then a Gainers / Losers row's `open` and
`gap_percent` are `null` (unknown, never 0); a repriced row takes the quote's
open over one it stored. A Gappers row's `gap_percent` is its `change_pct` --
the move against the prior close -- in its roster rows and in every
`price_patch` tagged `gappers` (`gapper_view.patch_for_table`); the patch used
to carry the Gainers row's open-based gap, so the Gappers table, the Focus rail
and the Trader tab showed yesterday's open-to-close move, frozen, and flipped
to the real move on each roster replace.

**Live rows state their halt** (#487, operator decision 2026-09-24): every row
`surface_rows` serves carries `halted: boolean | null` -- is the symbol halted
now -- read when the row is served, from memory only
(`ibkr.halt_status.halted_now`: no network or database wait, safe on the IB
loop). IBKR decides where Nova holds a live L1 line (session ready) whose
incoming tick 49 has reported: `0` is `false`, `1` / `2` `true`, `-1` or no
report yet no answer -- the Level 2 header's precedence. Otherwise the Nasdaq
Trade Halt RSS decides while it is answering (its last read succeeded and is
younger than `NASDAQ_TRADE_HALT_RSS_FRESH_SEC`): an open row (no trade
resumption, or one still ahead) is `true`, no open row `false` -- except while
the read lists a market-wide circuit breaker, which carries no end time, so
nothing reads `false` then. Anything else is `null`: not known, never "not
halted", and a halt is never inferred from quiet tape. It is a view over the
row, stamped on the served copy and never written into the cache (ADR 008);
The scanner socket also sends `halt_patch` (#571): `{type: "halt_patch",
rows: [{symbol, halted: boolean | null}], ts}` when tick 49 changes, on an RSS
refresh (including removals or an unavailable feed), and when an RSS answer
ages out. It updates only the served halt overlay, including a frozen table;
cache rows, membership, prices, metadata and timestamps stay untouched. A
history desk ignores live halt patches. The Scanner's Halted chip filters live and
played-back boards alike -- it keeps `true` and `null` and drops `false` -- and
a row stated halted shows the HALTED mark.

## Float credibility and short-interest dates (#532)

Every float and short-interest figure is Yahoo's (`fundamentals.py`). The
fundamentals payload (`fetch_fundamentals`; the ticker detail's `fundamentals`)
keeps `shares_outstanding` and adds `held_percent_insiders` (Yahoo's
`heldPercentInsiders`, a fraction: 0.128 = 12.8%), `short_interest_ts` (Yahoo's
`dateShortInterest`: epoch seconds of the FINRA settlement the short interest
is from), `float_contradicted: boolean | null`, `float_contradicted_reason:
string | null`, `short_above_float: boolean | null` and
`short_above_float_reason: string | null` -- each `null` when Yahoo gives none.
`short_ratio` is Yahoo's own ratio (short interest over Yahoo's average
volume), never FINRA's days to cover. A float is **contradicted**
(`fundamentals.float_credibility`, pure) when it is under
`FUNDAMENTALS_FLOAT_MIN_NON_INSIDER_SHARE` (0.5) of shares outstanding x (1 -
insiders): `true` when that fires, `false` when shares outstanding and insiders
are known and it does not, `null` otherwise; the reason names the counts. A
float above shares outstanding is never flagged -- the share count is the stale
field there and it cannot pass a low-float gate falsely. **Short interest above
the float is a warning, never a gate** (operator decision 2026-09-24: "make sure
it never blocks those setups, just gives an on-screen warning"):
`fundamentals.short_above_float` (pure) is `true` when short interest exceeds
the float, `false` when both are known and it does not, `null` otherwise. It
cannot tell a stale float from shares lent more than once, which is what a
heavily shorted name looks like, so no gate reads it: the desk shows the short
interest as "9.0M!" in amber with the reason first on its hover (scanner Short
Int., Fundamentals panel, Trader side column) and adds the reason to the float's
hover; `/api/why` facts carry `short_above_float` and the short-interest
check's `detail` adds the reason (its state is unchanged), as does the stock
read's short-interest row. Until 2026-09-24 (#532 follow-up) the same condition
also set `float_contradicted`, so a squeeze with more than 10M shares
outstanding could be refused a Low Float gate. Every scanner row
(`scanner_surface.surface_rows` -> `mover_enrich_view.decorate_rows`) adds
`shares_outstanding`, `short_interest_ts` (only while the row's
`short_interest` is the cached figure, else `null`: a date is never pinned on
another report), `float_contradicted` / `float_contradicted_reason` (judged on
the row's own float and shares outstanding) and `short_above_float` /
`short_above_float_reason` (the row's own float and short interest).

**Max-float gates read it** (#532 point 2, operator decision 2026-09-24: ship
it now). The fact that holds is float <= shares outstanding, so a contradicted
float passes a max-float gate only when `shares_outstanding` is at or under the
gate's limit; when shares outstanding is over the limit or unknown the float is
**unknown, and never a pass** -- not even where an unknown float passes. One
pure rule, `strategy/float_gate.float_for_gate(float, limit, contradicted,
shares_outstanding) -> (passes, reason)`, for every gate; a float whose check is
`false` or `null` (unchecked) is judged exactly as before. HOD Momo's
`max_float` (the "Low Float" strategies) refuses it `float:contradicted(shares_out=
<count>><limit> | unknown)` and queues no second Yahoo read; `TickerSnap` carries
`float_contradicted` / `shares_outstanding`, set with the float they describe
(the fundamentals enrichment loop and the after-hours runner; a float given
without its check -- a HOD replay's archived float -- is unchecked). The setup
grade's float pillar is `null` (unknown, never failed) and a template's stock
filter keeps the setup out even with `unknown_passes` (replayed eyes read the
check from the recorded leaderboard row). The Five Pillars float
pillar fails with the reason as its `detail`, and the Contenders float score is
0 (a rescued float scores on shares outstanding, the most it can be).
`LEADERS_RULES` refuses it `float_contradicted`. HOD Momo `min_float` and the
scanner's Float chip (a view filter that keeps what it cannot judge) still
compare the float as shown. On the 2026-09-23 audit at a 10M line: SECZ (8.45M
float, 163.27M out), RNAZ (2.15M, 16.93M), WNW (156K, 26.33M) and LGCL are
refused; WHLR (54K, 568K), HAO and HKIT pass.

The desk shows a contradicted float as "54.0K?" with the
reason on hover, and short interest with its settlement date ("566.0K (Aug
31)"; the scanner's second line "8/31 · 6.9") and Yahoo's ratio named on hover
and in the quote panel's "Short Ratio (Yahoo)".

**A filed share issuance is a warning, never a gate** (operator decision on #700, 2026-10-02: "warn, don't
block"). Yahoo's float and share count lag an issuance by weeks: after AMOD's 8-K of 2026-10-01 issued
51,621,560 shares for 3,170 bitcoin, Yahoo still read 4,966,818 outstanding and a 630,935 float. Owner
`catalysts/issuance.py` (in memory; re-read off the loop every `CATALYST_ISSUANCE_REFRESH_SEC` from the live
catalyst feed's store, one filtered query; a store not on disk leaves it empty): per symbol, the newest SEC 8-K
of the last `CATALYST_ISSUANCE_LOOKBACK_DAYS` (30) with Item 3.02, or with Item 2.01 that the catalyst rules
label a raise (`classify.shares_issued`). Every scanner row (`mover_enrich_view.decorate_rows`) and the ticker
detail's `fundamentals` (REST and the socket's `detail_update`) add `shares_issued: {published_ts, source, form,
items, title, url} | null` and `shares_issued_reason: string | null` ("Shares were issued per the SEC 8-K of Oct
1 11:30 ET (Items 2.01, 8.01): Yahoo's float and share count predate it. A warning only: no gate reads it"). The
desk reads the float as "630.9K?" with that reason first on hover (scanner Float, Fundamentals panel, Trader side
column), the stock read's Float row reads "630.9K?" (`warn`) and its rotation "81.9x today?", and `/api/why`'s
float checks read unknown (below). The figure is still Yahoo's: `float_contradicted`, the HOD Momo floats, the
setup grade, `LEADERS_RULES` and every max-float gate are unchanged, and nothing parses a share count out of a
filing (PIPE shares may not trade until a resale registration, so the tradable float is not known either way).

## Scanner leaderboard: recorded, reconstructed, played back (ADR 023, operator decision 2026-09-22)

Owner `backend/leaderboard/`; store `leaderboard.sqlite3` (`PRAGMA
user_version=3`, unknown versions refuse; a version-1 or -2 store is migrated
in place by creating the two catalyst tables below and adding the `rows`
columns `float_contradicted` / `shares_outstanding` (#532) -- nothing existing
is rewritten, and a row stored before reads both as `null`) under `NOVA_LEADERBOARD_DIR`, else
`F:\Nova\leaderboard` when F: is mounted, else `<cache_dir>/leaderboard` --
beside, never inside, the capture root or the historical downloads. One
**leaderboard row** per symbol per minute per board:

`{symbol, minute_ts, board, source, rank, price, prev_close, change_pct,
volume, rvol, rvol_basis, float_shares, float_contradicted, shares_outstanding,
has_news, news_first_seen_ts, halted, gap_pct, exchange, market_cap, catalyst}`
-- `minute_ts` is a whole-minute epoch second
and the row is the board **as it stood at `minute_ts`** (a reconstructed row
uses only minute bars that closed by then; a recorded row is the desk's board
snapshotted within `LEADERBOARD_RECORD_SETTLE_SEC` after it). `source` is
`recorded | reconstructed`; `board` is `gappers | gainers | losers |
afterhours | large_cap` (recorded: the desk's lists through
`scanner_surface.surface_rows`, so blocklisted names never appear); a
reconstructed day writes `market` (the whole market, shown as Gainers),
`losers` and `gappers` ("A rebuilt day's lists" below). `change_pct` is a fraction against the
prior close, computed from `price` and `prev_close` and `null` when either is
unknown (a `close_fallback` row has no print: `price` / `change_pct` null).
`rvol_basis` is `daily_avg` (the desk's RVOL: volume over the average daily
volume) or `time_of_day_20` (volume so far over the same-minute average of the
prior 20 sessions); two bases are never compared. `float_shares` is as known
that day or `null`; `float_contradicted` (`boolean | null`) and
`shares_outstanding` are a recorded row's float check as the desk row carried
it that minute (#532, "Float credibility and short-interest dates"; a row
recorded on 2026-09-24 before the short-interest warning was split out may
carry `true` for short interest above the float alone),
`float_contradicted` `null` without a float; a reconstructed row carries
neither. `has_news` / `news_first_seen_ts` only from news seen by
that minute. Every unknown is `null`, never a placeholder. `halted` is derived
at read time from the halt log: `true` while a logged halt is open, `false`
only for a recorded minute whose halt feed was answering, else `null` (a live
row states it by the same rule from the live sources: "Live rows state their
halt" above).
`catalyst` is derived at read time too ("Catalysts in playback" below).

**Catalysts in playback** (#498). The research backfill's store is never read
by the backend (ADR 024), so `research/catalysts/export_leaderboard.py` copies
what playback needs into this store, per symbol-day it holds (its `targets`):
`catalyst_checks (session_date, symbol, window_start, window_end,
sources_answered, rules_version, exported_ts)` -- the window (the prior
session's 16:00 ET close to 20:00 ET) and the sources whose check was `ok`,
comma-joined, `''` when none looked -- and `catalyst_items (session_date,
symbol, item_id, published_ts, source, publisher, title, url, kind, category,
strength, dilution, rules_version)`, every item naming the symbol in that
window labelled by `catalysts/classify.py` at the export's rules version
(labels, not article text; Finnhub's Benzinga copies left out, #516). The
export replaces each symbol-day whole, one session day per transaction; it is
the tables' only writer. A board read gives each row `catalyst: verdict | null`
in the live desk's wire shape (`catalysts/live.WIRE_KEYS`), computed by
`leaderboard/catalyst_verdicts.py` with `classify.verdict_from_labels` -- the
live verdict's own ranking -- from the items published after the window opened
and at or before `at` (never after; the window's end when `at` is later), so
`rules_version` is the export's. `null` when the symbol-day was not exported,
or when no source looked and nothing was published by `at` -- unknown, never
"no news"; a checked symbol with nothing published yet is `none_found`.
`news_pending` / `halt_code` come from this store's `halt_events` (a Nasdaq T1
/ T12 halt that started inside the window with no resumption logged by `at`).
On the desk, after a merge that changes the rules or a new fetch, the operator
runs `py -3 research/catalysts/export_leaderboard.py` (research store
`F:\Nova\catalysts\catalysts.sqlite3`, leaderboard store
`F:\Nova\leaderboard\leaderboard.sqlite3`; `--db` / `--since YYYY-MM-DD`).

**Gap policy.** The recorder runs whenever the backend runs -- no button --
and writes, each minute 04:00-20:00 ET on exchange days, one `minutes` row
(`run_id`, `feed_live`, `halt_feed_ok`) and one `coverage` row per board
(`state: live | frozen | unavailable | feed_down`, `row_count`); a
reconstructed day writes `coverage` per board with `state: rebuilt` (`frozen`
for its Gappers from 09:30). A minute without a
`minutes` row was not recorded. Playback never carries a board across a gap:
the board at a playhead inside one is `null` with `gap: {reason, start, end,
stop}`, `reason` one of `not_running | feed_down | not_recorded |
outside_session` (`start` / `end` null for `outside_session`), `stop` --
for `not_running` -- `shutdown` (Nova was closed) | `unexpected` | null.
`runs` rows (`run_id`, `started_ts`, `last_beat_ts`, `stopped_ts`,
`stop_reason`) say whether Nova closed or stopped unexpectedly. Rows are
enqueued, never written on the IB loop (ADR 010).

**Halt / LULD log.** `halt_events` rows `{symbol, ts, event: start | end,
kind, code, source: ibkr_ticker_halted | nasdaq_trade_halt_rss,
session_date}` from IBKR tick 49 transitions and Nasdaq Trade Halt RSS rows.
A halt is never inferred from a gap in the prints.

**One ranking** (`leaderboard/ranking.py`, pure): qualify, then order by
`change_pct` (ties: volume, symbol; worst first under `worst_first`). Playback's `leaders`, the S5 offline
universe, the rebuild and live auto-record call the same function; presets are
`BOARD_RULES`, `LEADERS_RULES` ($3-10, float <= 10M or unknown, volume >=
100k, top 3), `S5_RULES` (top 3 with `time_of_day_20` RVOL >= 5),
`LOSERS_RULES` (a known change under 0, worst first) and `GAPPERS_RULES` (the
live premarket Gappers floor, `ibkr/gapper_view.row_qualifies`: price >=
`SCANNER_MIN_PRICE`, `change_pct * 100 >= GAPPER_MIN_GAP_PCT`). Under
`LEADERS_RULES` a contradicted float (#532) qualifies only on shares
outstanding <= 10M and is otherwise refused `float_contradicted` -- an unknown
float is admitted, a contradicted one is not, because its own counts say it is
likely larger than shown; a row without the check (reconstructed, or recorded
before schema 3) is judged as before. Playback and auto-record read the same
stored check, so they still agree on who led. A
recorded row's `rank` is the desk's own order of that list (Losers stay
worst-first); a reconstructed row's `rank` is its board's: `BOARD_RULES` on
`market`, `LOSERS_RULES` on `losers`, `GAPPERS_RULES` on `gappers` (from 09:30
the 09:30 order).

**A rebuilt day's lists** (ADR 023 amendment 2026-10-06; operator report:
"Don't we already have the data for this day ... Why do we not see gainers,
losers, and gappers for that hour?"). A rebuilt day kept only `market`, the top
100 risers each minute, shown as Gainers: 2026-09-09 held no row under 0% at
07:00, 09:45 or 16:30, so it had no Losers, and nothing projected its Gappers.
`research/leaderboard` writes three boards per minute from the same rows (every
universe symbol with a closed bar by the minute):
- `market`: the top `--top` by `BOARD_RULES`, plus every `LEADERS_RULES` /
  `S5_RULES` pick (unchanged);
- `losers`: the bottom `--top` by `LOSERS_RULES`, ranked 1 = worst;
- `gappers`: before 09:30 the top `--top` by `GAPPERS_RULES`, `gap_pct` the
  move (the live list's own number before there is an open); from the 09:30
  minute, built from premarket bars only, its membership and order are frozen
  as the live list freezes, and each later minute reprices those symbols
  (`state: frozen`).

Each board writes a coverage row every minute, so an empty list reads as empty,
never as not rebuilt. A day counts complete for `--skip-complete` only when all
three boards cover its 960 minutes. On the desk a rebuilt day fills Gainers,
Losers and Gappers; Losers and Gappers on a day rebuilt before say so. After
Hours and Large Cap are not rebuilt, and each says why: the live After Hours
list is IBKR's after-hours gainers, ranked on the move since the regular close,
which the rebuild does not measure; Large Cap needs a market cap as of the day,
which the files do not carry.

**Splits a rebuild confirms from SEC filings** (#772). A rebuilt day adjusts its
prior close and RVOL lookback for the splits in Massive's split list, so a split
missing there reads as a fake mover: PHGE's 1-for-10 reverse split on 2026-09-09
read +925%. `research/leaderboard/confirm_splits.py` adds the splits SEC filings
prove, and only those:
- **Suspects.** For each pair of sessions in a span, a common / ADR ticker whose
  open is at least 1.8x, or at most 0.7x, the prior close, with no split listed
  between them.
- **Filings.** The ticker's 8-K / 8-K/A with Item 5.03 or 3.03, or 6-K / 6-K/A,
  filed from 60 days before to 3 days after the session. The list comes from the
  bulk `submissions.zip` on F: (the live submissions JSON past the file's date);
  the documents (primary, then EX-99) are fetched from SEC and cached by accession.
- **What confirms.** A sentence about a reverse / forward split or a share
  consolidation states a ratio outside any range ("one-for-ten reverse stock
  split"); several ratios in a filing (a past split mentioned) leave the one the
  price agrees with. The split-adjusted open must be 0.5-2x the prior close, and
  a date the filing names beside "effective" / "split-adjusted" / "begin
  trading" must fall after the prior session and by the session. With no such
  date the band is 0.67-1.5x; a filing that names only other dates is refused.
  A suspect whose ticker has a split listed within 10 sessions is reported,
  never added: it would adjust twice.

Confirmed splits live in `F:\Nova\leaderboard\splits_confirmed.json` (beside the
store, `NOVA_LEADERBOARD_DIR`): `{schema_version: 1, updated_at, spans: [{start,
end, checked_at, suspects, with_filings, confirmed, refused}], splits: [{ticker,
execution_date, split_from, split_to, cik, form, items, accession, filed, url,
ratio_text, date_match: boolean | null, prev_session, prev_close, open,
price_ratio, adjusted_ratio, volume_ratio}], refused: [{ticker, execution_date,
accession, reason}]}` -- `split_from` / `split_to` in Massive's convention (a
1-for-10 reverse split is 10 / 1), `date_match` null when the filing names no
effective date. A run replaces its span's entries and keeps every other; an
unknown version refuses. `lb_io.load_splits` adds them to Massive's list
(Massive's entry wins on the same ticker and day), and `spot_check.py` reads
them too. The tool prints the rebuilt days a new split touches -- its day, and
the next 20 sessions the ticker traded (the RVOL lookback) -- for
`build_leaderboard.py --dates`.

**Routes.** `GET /api/leaderboard/days` -> `{schema_version, store: {path,
ok, error}, days: [{date, recorded: {minutes, first_ts, last_ts, boards} |
null, reconstructed: {minutes, first_ts, last_ts} | null}]}` newest first.
`GET /api/leaderboard/{date}?at=<epoch>&source=` -> `{schema_version, date,
at, source, minute_ts, covered, gap, boards: {BOARD: {state, rows[]}},
leaders: {board, symbols[], rules}, catalyst_symbols}` -- the board at the latest minute at or
before `at` (never after); `source` defaults to `recorded` when that day has
one, else `reconstructed`; `catalyst_symbols` counts the day's
`catalyst_checks` rows (`0`: no catalysts on file for the day, and the
Scanner's Catalysts tab says so in Sim). `GET /api/leaderboard/{date}/coverage?source=` ->
`{date, source, session_open, session_close, spans: [[start, end], ...],
gaps: [{start, end, reason}]}` (whole epoch seconds). `GET
/api/leaderboard/{date}/halts?until=<epoch>` -> `{date, events[]}`. `GET
/api/hod-momo/history/{date}` accepts `?until=<epoch>` (alerts raised at or
before it, by `created_ts`, else `timestamp`; the reply stays a bare list). `GET /api/history/dates?type=all` lists every date with any saved
board; `type=movers` reads the `gainers-` / `losers-` files. `/api/ibkr/status`
adds `leaderboard_recorder: {recording, ok, error, since, run_id}`.

**Auto-record.** The backend records, first, the setups of the templates in
play that are in a scored trade (`trade`), near their trigger (`near`) or armed
(`armed`) -- whenever any setup's template in play is inside its arming window
(07:00-11:30 ET by default; red to green 09:30-10:30; the 5-minute flat top 07:00-15:30; ADR 042: until then a
setup arming after 10:00 had no line, and red to green's triggers were never
"go") -- then, 07:00-10:00 ET only, the top
`LEADERBOARD_AUTO_RECORD_TOP_N` `LEADERS_RULES` names of the live Gainers
board (ADR 041: the tape at a setup's trigger and through its trade is what the
signal trials read). At 10:00 only the leaders' lines stop. A setup takes a
leader's line once that line has run
`LEADERBOARD_AUTO_RECORD_SETUP_MIN_KEEP_SEC`, never another setup's; a trade
keeps its line past its window until its scoring window ends. It records
through the Session Record path, using only **free** Level 2 lines
(`IBKR_MAX_DEPTH_SYMBOLS` total), and yields its lowest-ranked line the
moment the operator opens Level 2 on another symbol -- the operator never
loses Level 2 (operator decision 2026-09-22). It never starts, stops or
adopts a symbol the operator recorded by hand; its stops are planned
(`reason: "auto"`, excluded from `missing_sec` like `operator`), never a loud
unrequested stop; the operator pressing Record also takes a line back, and a
symbol the operator stopped is not retaken that day. A line it gives back to the
operator -- for Level 2, a Record, or a Time & Sales IBKR refused for its
tick-by-tick cap (#698) -- is cancelled at once, never after the tape's 16 s
remount linger, and stays theirs `LEADERBOARD_AUTO_RECORD_YIELD_HOLD_SEC` (30 s)
while their subscribe lands (on 2026-10-02 the next tick took TNON's line back
before AIXI's Level 2 had it). It never takes a slot a restart's resume is
bringing back (`keepalive.pending_symbols()`). **What it holds survives a
restart** (#698; owner `leaderboard/auto_record_state.py`): `auto-record.json`
in the operator cache, `{schema_version: 1, date: "YYYY-MM-DD" (Eastern), held:
{SYMBOL: {since: number | null, why: "trade" | "near" | "armed" | "leader" |
null}}, declined: string[], operator: string[]}` (`operator`: the recordings the
operator started or took over today; a file without it names none), rewritten on
every start, stop, operator take and operator stop; another day, an unknown version
or an unreadable file reads as empty (logged). After a restart a recording it names
that the keepalive resumed is auto-record's again (so it can rotate it or give it
back), and a symbol the operator stopped stays declined that day. **The stock you
look at always outranks a recording you did not start** (operator, 2026-10-02:
"when I view a stock or a ticker, the recorder will empty a space for me"): a
recording a restart brought back (`keepalive.restart_symbols()`) that the file does
not name as the operator's is auto-record's too, so it gives way to the operator's
Level 2 and stops at its window's close. At 10:36 that day the backend came up on
the first build with the file, the process before it never wrote one, and SDEV,
SSM and CELU -- all auto-record's -- read as the operator's: AZTA's Level 2 read
"Symbol cap reached" for over an hour. When every line is still in use, the
ladder's refusal names who holds each (`line_lending.view.cap_words`: recording,
another Level 2, lent, replay) and how to free one, and it asks again every 1, 2,
4, then 5 s -- it had asked every second. `NOVA_AUTO_RECORD=0`
turns it off. `/api/ibkr/status` adds `auto_record: {active, window,
windows: {open: "setups_and_leaders" | "setups" | "leaders" | "none", setups: {open,
start, end, by_setup: [{setup, start, end, open}], error}, leaders: {open, start,
end}}, symbols[], why: {SYMBOL: "trade" | "near" | "armed" | "leader" | "left"},
setups: [{symbol, why}], setups_error: string | null, leaders[], yielded[],
last_error}` (`setups_error`: the setup scanner could not be read -- stated,
never read as "no setups"); the operator taking a line back gives up the
lowest-ranked first (`left`, then `leader`, `armed`, `near`, `trade`); `/api/diagnostics` adds the
`leaderboard_recorder` and `auto_record` rows (group `recorder`).

**Retention: keep everything, guard the drive** (operator decision on #485,
2026-09-24). Nothing deletes leaderboard rows automatically -- recorded days
cannot be replaced, a rebuild takes about a minute a day, and SQLite gives no
space back without a `VACUUM` of the whole file. The store grows about 6-9 GB
a year. The `leaderboard_recorder` row's `evidence` adds `store_bytes`
(`leaderboard.sqlite3` plus its `-wal`; `0` before the store exists),
`free_bytes` (free space on the store folder's volume, `shutil.disk_usage`)
and `disk_error` (`string | null`), read on the checklist's worker thread. The
row is `warn` under `LEADERBOARD_FREE_WARN_BYTES` (50 GB) free and `fail`
under `LEADERBOARD_FREE_FAIL_BYTES` (10 GB), with the room left and the fix
(free space, or move `NOVA_LEADERBOARD_DIR`); a size or free space that cannot
be read is `unknown` with the reason, never `ok`. The drive's verdict only
ever makes the row worse: a write failure stays `fail`, and with room to spare
the row reads as before.

**Sim day.** `POST /api/sim/clock {session_date: "YYYY-MM-DD" | null}`
re-dates the Sim clock with nothing loaded -- any loaded replay, of that day or
another, is unloaded (never deleted) so the clock opens the full 04:00-20:00
session (operator decision 2026-09-22) -- and parks it paused at
`SIM_DAY_JUMP_PARK_MIN_ET`; `null` returns to today, unloading a replay of
another date. Off the live edge the Scanner board and the HOD Momo strip read the
leaderboard and the alert history at the playhead; Live and Paper stay on now.
The Sim Day calendar marks, per day and each from its own source, a board
recorded by Nova, the operator's usable Session Records (`/api/capture/sessions`)
and a rebuilt board; a day with none, a weekend or a future day cannot be picked.
`/api/leaderboard/days` lists every day on file (`LEADERBOARD_DAYS_LIMIT` 2,500).

## Watchlist rows (operator decision 2026-09-23)

`GET /api/strategy/watchlist` entries keep `symbol`, `composite_score`,
`sub_scores` and `five_pillars`, and add the scanner row's own market facts --
`price`, `change_pct` (a fraction against the prior close, also past +100%),
`rel_volume`, `rvol_source`, `float_shares`, `has_news` (the scanner's article
flag) -- each `null` when unknown, never a placeholder, and `catalyst:
{verdict, category, strength, title, source, published_ts, news_pending} |
null`: today's verdict from `catalysts/live.py` (ADR 024), `null` while no
source has looked (unknown, not "no news"). Asking queues the Alpaca fetch in
the background (`strategy/watchlist_catalyst.py`); the route never waits on
the network. The Watchlist table joins the setup board (`/ws/setups`) and the
bot allowlist by symbol on the client; nothing on the Watchlist places.

**Any symbol's pillars (operator ask 2026-09-23).** `GET
/api/strategy/watchlist/{symbol}` (owner `strategy/symbol_pillars.py`,
read-only, no network wait) answers `{note, symbol, source, rank, entry}` --
`entry` a watchlist entry as above, graded from the symbol's own scanner row
when a board holds it (`source`: `gappers` | `gainers` | `losers` |
`afterhours` | `large_cap`, surfaced exactly as the Scanner shows it), else from
its live L1 quote decorated the same way (`source: "quote"`: price, volume and
the line's tick-9 prior close from `ibkr.ticks.last_quotes`, whose rows add
`prev_close` once IBKR sends it; float / RVOL from the fundamentals cache; the
catalyst verdict read before grading). `rank` is its 1-based place on the
ranked watchlist, else `null`. A fact nobody holds stays `null` and its pillar
fails with that reason. The quote panel's Watchlist strip uses the ranked entry
when there is one and this route for every other symbol.

