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

Results as produced: `results_*_2026-09-23.json` beside this file.
