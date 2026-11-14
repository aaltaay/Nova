# Data schema: trade journal statistics

Owner: `backend/journal/metrics.py`, exposed by `backend/routes/journal.py`.

`GET /api/journal/metrics?include_mock=false` returns:

```text
{includes_mock_data: boolean, total_closed_trades: integer,
 win_rate_pct: number | null, avg_win_dollars: number | null,
 avg_loss_dollars: number | null, profit_loss_ratio: number | null,
 total_pnl_dollars: number | null, adherence_pct: number | null}
```

Only closed trades count. Mock rows are excluded by default, and included only when requested and labeled.
Missing rates remain null, never invented. The counts, P/L ratio and adherence percentage are measurements
for the operator to interpret. They never decide trading eligibility.

Operator decision 2026-10-13 (#791): remove `go_no_go` and its sample/adherence/profitability thresholds and
remove the Journal's Live-money GO/NO-GO bar. No readiness verdict, Paper sample or review/drill checklist
may grant or refuse permission. Explicit operator Live opt-ins/PIN and broker/account/order safety remain.
This read-only route never places an order. Existing journal rows require no migration.

## The trade list and its filters (search gaps, operator 2026-10-26)

Owner: `backend/journal/store.py` (`get_trades`), exposed by `backend/routes/journal.py`.

`GET /api/journal/trades?limit=&include_mock=&symbol=&setup=&tag=&adherent=&date_from=&date_to=` returns
`{count, includes_mock_data, filters, trades[]}`, the newest `limit` trades (default 200) that match every filter
given: `symbol` and `setup` exact (case ignored), `tag` one of the trade's tags (case ignored; the limit counts
matches), `adherent` `true` | `false` (the plan flag; a trade with none matches neither), `date_from` / `date_to`
the ET day the trade opened (`YYYY-MM-DD`, inclusive; another shape is a 400). `filters` echoes the filters given
(`{}` when none). Additive: an ask without filters answers as before, plus `filters: {}`. Read-only.

## Your trades and the bots' on the Reports tab (ADR 069 decision 6, #1267)

Owner: `backend/journal/paper_trips.py` (Paper's round trips), `backend/journal/store.py` (the columns and
filters), `backend/journal/split.py` (yours and the bots' beside each total), exposed by
`backend/routes/journal.py`. Design: mockup `F:\Nova\design\bot-human-books\reports-v1`, approved 2026-11-04.

**Three columns** on `trades`, added by `journal.db._TRADES_MIGRATIONS` (`ALTER TABLE ... ADD COLUMN`, no data
loss, nothing rewritten): `venue` (`paper` | null), `owner` (`you` | `bots` | null) and `bot` (the holder inside
the bots' book: `bot` the strategy bot, `auto_entry`, `bot_api`, `live_trader`, `claude`; null for yours). A row
from before stays null, and a null `owner` reads as yours (ADR 063's rule). Every trade dict the journal returns
carries the three.

- **IBKR round trips** (`journal.round_trip`) keep `venue` null and take `owner` / `bot` from the execution row
  that opened the round trip: `owners.whose.holder_of_order(source, payload.origin, payload.bot_id)`. Imported
  files (`journal.import_apply`, `journal.ibkr_import`) are yours: `owner` `you`. Demo rows stay null.
- **Paper's round trips** (`venue` `paper`) are built from the practice ledger and its archives, never inside a
  fill: `practice.history.ledger_fills` gives every fill's `parts` (ADR 069's split, each at its holder's own
  cost), and each holder's shares in a stock make one round trip from leaving zero to returning to it. So two
  holders trading SOFI at once are two trades, and Nova's own closes (KILL, the day cover) close each holder's
  own. `qty` is the shares closed, `entry_price` / `exit_price` the average fill prices in and out, `pnl` the sum
  of the parts' `realized` (net of commission and fees, so the trades add up to the books' realized), to the
  cent, `commission` the parts' commission plus fees, `fill_ids` the order ids, `opened_ts` / `closed_ts` the first
  and last fill. `stop_price` is the stop leg sent with the entry (`leg_role` `stop`, `parent_id` the opening
  order), when it sits on the losing side of the entry; otherwise null, and R-multiples skip the trade. `setup`
  and `tags` start empty (Paper's orders carry none). `close_key` is
  `paper:<ledger created_ts>:<holder>:<symbol>:<opening order id>:<opening fill ts>`. A holder's position still
  open is not written.
- **Written on read.** A Reports read with `venue=paper` first brings the journal up to the ledger
  (`paper_trips.sync`): new round trips are added and a stored one whose figures changed is updated by
  `close_key` (the ledger's figures win; `tags`, `notes` and `adherent` stay). Nothing is deleted. It runs once
  per ledger change (one lock, keyed by the journal file, each ledger's `created_ts` and event count), so the
  first open fills in every past Paper day (ADR 069 decision 7) and a poll with nothing new writes nothing.

**Reading by venue and view.** `GET /api/journal/calendar`, `/tags`, `/r-multiples`, `/drawdown` and `/trades`
accept `venue` (`live`, the default, or `paper`), `owner` (`you` | `bots`) -- another value of either is a 422 --
and `bot` (a holder; implies `owner=bots`). `venue=live` is every row that is not Paper's: IBKR round trips
and imported files, the journal as it was. The risk engine (`strategy.risk.reconstruct_from_journal`),
`/api/journal/metrics`, the trail, the net P&L repair, tape labelling and the research front door's
`journal_trades` read only that, unchanged. `owner=you` matches `you` and null. With `include_mock=true` the
demo rows show on either venue. Each answer echoes `venue` and `view: {owner, bot}`.

**Yours and the bots' beside each total.** With `venue=paper` and no `owner` / `bot` (the All view), each
aggregate carries `by_owner: {you, bots}`, the same figures over each book's trades:

- calendar: each day, week and month, the year (`year_pnl`, `year_trade_count`), `best_day` and `worst_day`:
  `by_owner: {you: {pnl, trade_count}, bots: {pnl, trade_count}}`;
- r-multiples: `by_owner: {you, bots}`, each `{trade_count, scored_count, skipped_no_stop, expectancy_r,
  avg_win_r, avg_loss_r}`;
- drawdown: `by_owner: {you, bots}`, each `{trade_count, final_equity, peak_equity, max_drawdown,
  max_drawdown_pct}`, and every `curve[]` point adds `owner` and `bot`, whatever the view.

Tags carry no split: a tag's row counts the trades the view shows. The year calendar on Paper also carries
`holders: [{owner, bot, trade_count}]`, every holder with a closed trade that year whatever the view, yours
first, then the bots by count (the switch's Bots menu). Live and Sim answer without `by_owner` and `holders`.

**The tab** (`frontend/src/reports/`) follows the Account page's venue and its All / You / Bots switch, one pick
for Overview and Reports, opening on All. Paper reads `venue=paper` with the view, and its Import row says an
import is Live's. Live reads the journal as before, with the switch shown as You and disabled
(`OWNER_LIVE_WHY`). Sim is unchanged: no switch ("Leave the sim alone").

## Three traders and Earlier bots on the Reports tab (ADR 072)

**Confirmed for the build; replaces the section above when its batch lands.**

- **The columns.** `owner` is `you` | `claude` | `brain` | `earlier_bots` | null (null reads as yours); `bot` is set
  only for `earlier_bots` (`bot`, `auto_entry`, `bot_api`, `live_trader`). One more column, `closed_by` (`you` |
  null), added by `journal.db._TRADES_MIGRATIONS` (no data loss). Stored rows are read through `owners.whose`: a row
  with `owner` `bots` and `bot` `claude` reads as `claude`, any other `bots` row as `earlier_bots`; the next Paper sync
  writes them so.
- **Round trips** are built per holder as before, from the same `parts[]`; a round trip whose closing parts carry
  `closed_by: "you"` is stamped `closed_by: "you"` and stays on the trader's record. Sim's trades are not written
  to the journal (a rewind unwinds them); Sim's books show on the Account page from the account and history wire
  (`recording-and-replay.md`, "Three traders' books").
- **Reading by view.** `owner` takes `you` | `claude` | `brain` | `earlier_bots` (another value is a 422); `bot`
  narrows Earlier bots only. With no `owner` (All), each aggregate's `by_owner` is `{you, claude, brain,
  earlier_bots}`; `holders` lists every owner with a closed trade that year. Live answers without them, as before.
- **The tab** reads All / You / Claude / The brain / Earlier bots on Paper, opening on All; Live shows You,
  disabled, with its reason.
