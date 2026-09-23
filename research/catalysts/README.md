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
| `py -3 research/catalysts/build_verdicts.py` | a verdict per target with the current rules version; coverage to `results/coverage.json` |
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

## Findings, 2026-09-23 (rules v3)

**Coverage.** 7,976 symbol-days (5,733 pillar candidates, 1,931 leaderboard movers, 312 both).
Of the 2,243 rebuilt-leaderboard top-10 movers, the Massive archive alone had no article for 95%;
with the four sources 30% have none found, 236 carry a strong catalyst and 648 a weak one. EDGAR's
filed release is the representative item for 2,426 symbol-days. Finnhub (one year) was still
filling (1,709 of about 3,500 in reach) -- re-run `fetch_finnhub.py` then `build_verdicts.py`.

**Accuracy** (`results_labels_2026-09-23.json`; labeller: Claude, blind -- operator labels are the
real test). On 200 items never used to tune the rules: 83% agree on kind; catalyst precision
77%, recall 94%; **strong catalyst precision 92%**, weak 73% (the misses are minor company items --
pre-IND filings, enrollment milestones, CEO letters -- rather than noise).

**First pullback by catalyst** (`results_split_fp_all_2026-09-23.json`; 1,017 trades on the
no-news universe, all -0.37R): strong catalyst at 09:30 -0.19R (180 trades, PF 0.84); weak -0.37R;
noise only -0.47R; none found -0.44R (PF 0.27); a strong catalyst with dilution the same morning
-0.60R; clinical data +0.05R (55 trades). A real catalyst roughly halves the loss (about 1.6
standard errors -- suggestive, not proof); it does not make the mechanical pullback pay.
