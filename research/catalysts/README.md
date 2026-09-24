# Catalysts -- the backfill on F: and the split by catalyst class (ADR 024)

Is a small-cap mover's news a real catalyst, a dilution notice, routine, noise -- or is there
none? The classifier is the live desk's own (`backend/catalysts/classify.py`); this folder
backfills the history it judges, onto the operator's F: drive, and splits setups by it.
Research only: nothing in `backend/` imports this folder, and nothing here places orders.

Store: `F:\Nova\catalysts\catalysts.sqlite3` (`NOVA_CATALYST_DIR` overrides; schema in AGENTS.md
section 3, "Catalysts"). SEC's bulk `submissions.zip` lives beside it under `edgar/`.

| Step (repo root) | What it does |
|---|---|
| `py -3 research/orb/select_gng.py --top 10000 --no-float --no-news --table pillars_all` | the Five Pillars gap universe **without** the any-article news pillar |
| `py -3 research/orb/extract_minutes.py --selection pillars_all --table minutes_pillars_all --start 04:00` | its minute bars |
| `py -3 research/catalysts/build_targets.py` | symbol-days to explain: that universe (cutoff 09:30) + the rebuilt leaderboard's top-10 movers (cutoff = first top-10 minute) |
| `py -3 research/catalysts/import_massive.py` | the Massive news archive already on F: (no network) |
| `py -3 research/catalysts/fetch_alpaca.py` | Alpaca / Benzinga newsroom, one session day per request batch |
| `py -3 research/catalysts/fetch_finnhub.py` | Finnhub free tier (one year back; older days recorded `out_of_range`) |
| `py -3 research/catalysts/fetch_edgar.py` | SEC filings in each window, with the filed press release (EX-99) of every 8-K / 6-K; needs `edgar/submissions.zip` from `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` |
| `py -3 research/catalysts/backfill_halts.py` | Nasdaq's halt page per date into `halts/raw/`, then the leaderboard's `halt_events` (Sim playback shows them) |
| `py -3 research/catalysts/build_shares.py` | `sec_shares` (shares outstanding as filed, from SEC's `companyfacts.zip` on F:) and `short_interest` (FINRA) into `orb.duckdb` |
| `py -3 research/catalysts/import_feed.py` | the desk's live catalyst feed (SEC + wires, `catalyst_feed.sqlite3`) folded into this store |
| `py -3 research/catalysts/build_verdicts.py` | a verdict per target with the current rules version; coverage to `results/coverage.json` |
| `py -3 research/catalysts/export_leaderboard.py` | every target's checks and labelled items into the leaderboard store (`catalyst_checks` / `catalyst_items`, #498), so Sim playback of a past day shows each mover's catalyst as known at the playhead; replaces each symbol-day whole -- re-run after a fetch or a rules bump |
| `py -3 research/catalysts/labels.py export` / `score <csv>` | the hand-labelled accuracy check (blind sample; labels in `label_kind`) |
| `py -3 research/momentum/backtest_setups.py --tag fp_all --set universe=pillars_all bars_table=minutes_pillars_all` | the first pullback on the no-news universe |
| `py -3 research/catalysts/split_trades.py --tag fp_all` | its trades by verdict at 09:30 and at each entry, and by catalyst class |

Every fetcher is resumable (answered targets are skipped, `error` rows retried). Set
`SEC_USER_AGENT` in `.env` to your own contact ("Name email") -- SEC asks automated clients to
identify themselves; the default is a placeholder.

Rules: a window opens at the prior session's 16:00 ET close; an item counts only if published
at or before the cutoff (never later -- no hindsight). `none_found` means the sources that
answered found nothing; a source that could not reach the date did not answer.

Results as produced: `results_*_2026-09-23.json` beside this file (numbers only -- the labelled
headlines stay on F:, they are publishers' text).

## Correction, 2026-09-23 evening (rules v6, #516)

Finnhub stamps its Benzinga copies with Eastern time read as UTC -- four hours early -- so the v4
numbers below let some verdicts read an article before it was published. Every reader now leaves
those copies out (`store.HONEST_CLOCK_SQL`; Alpaca carries the same articles with the right clock),
and rules v6 reads the cause a one-ticker "why is it moving" piece names in its summary. The
`results_*` files beside this README are the v6 run.

- **Leaderboard movers (2,243):** 40% none found (was 23%), 16% noise only (was 29%), 38% a
  catalyst (was 44%: 11% strong, 27% weak). Most of the old "noise only" and part of the old
  catalysts were Benzinga items that had not been published yet at the mover's cutoff.
- **Pillar universe at 09:30:** 2% of verdicts changed.
- **First pullback:** unchanged -- strong catalyst at 09:30 -0.21R (187 trades, PF 0.81), weak
  -0.36R, noise only -0.47R, none found -0.41R.

## Findings, 2026-09-23 (rules v4)

**Coverage.** 7,976 symbol-days (5,733 pillar candidates, 1,931 leaderboard movers, 312 both), every
source answered (Finnhub for its one year: 3,490 in reach, 4,486 out of range). Of the 2,243
rebuilt-leaderboard top-10 movers, the Massive archive alone had no article for 95%; with the four
sources 23% have none found, 260 carry a strong catalyst and 709 a weak one. Nasdaq's halt history adds 91,695 events (2021-10 on) to the
leaderboard's halt log -- 36,320 LULD pauses, 5,089 resolved news halts (T3).

**Accuracy** (`results_labels_2026-09-23.json`; labeller: Claude, blind -- operator labels are the
real test). Each holdout was scored once before the rules were tuned on it. On the last, never
tuned on: 85% agree on kind; catalyst precision 77%, recall 99%; **strong catalyst precision
92%**, weak 73%. The weak tier plateaus: each round fixes the fluff it sees and new fluff appears.
An unplaced single-company headline (`company_news`) was right about half the time over all 800
labels, so the live News pillar treats it as unknown.

**First pullback** (`results_split_fp_all_2026-09-23.json`; 1,017 trades on the no-news universe,
all -0.37R), each fact as known before the trade:

- catalyst at 09:30: strong -0.21R (187, PF 0.83) · weak -0.37R · noise only -0.45R · none found
  -0.44R (PF 0.26) · strong with same-morning dilution -0.56R · clinical data about break-even.
- shares outstanding (SEC, filed before the day): 5-20M the worst (-0.61R, 15-20% winners); low
  shares with no news -0.82R (37 trades, 11% winners); 20-50M -0.20R.
- short interest (FINRA, lagged 14 days): 5-15% of shares -0.25R; days to cover 3+ -0.26R vs 1-3
  -0.45R.
- halts before the entry: a news halt only 6 trades (too few to read); a LULD pause -0.30R.

A real catalyst roughly halves the loss (about 1.6 standard errors -- suggestive, not proof); a low
share count without news is the worst cell. None of it makes the mechanical pullback pay.
