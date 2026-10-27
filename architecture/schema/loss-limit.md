# Data schema: The daily loss limit

## One daily loss limit (ADR 056, operator decisions 2026-10-15)

One dollar line for every account -- Live, Paper and Sim -- that counts your trades and the bots'
alike: since ADR 063 the **Account** line, beside a line for your trades and one for the bots' ("Three
lines" below). It replaces the bot trip and the all-stop (ADR 032, superseded). Owner: `backend/loss_limit/`.

**What it counts** (`loss_limit/count.py`, pure). Per account, the trades opened today (from 04:00 ET,
`practice.clock.day_start_ts`, the plain calendar clock -- it turns on a Saturday and a Sunday too, where Day P&L and the
boards walk back to Friday's session (`practice.clock.session_day_start_ts`, 2026-10-19); whether this reset should walk
back as well is the operator's decision, not changed here): for each stock with fills today, the cash those fills moved (a buy pays, a sell
receives), less their commissions and fees, plus the shares still held at the account's own mark. A
stock the account already held when the day began -- its shares now less today's net fills is not
zero -- never counts and is never sold, however it was traded today. An open position with no usable
mark makes the figure unknown (`pnl: null`, `unknown` says why); an execution whose commission IBKR
has not reported counts without it (`costs_unknown`, a count of such fills).

- **Paper**, and **Sim while the desk is on Sim at the live edge**: the practice ledger's orders filled
  since its day began (`fill_ts`, `filled_qty`, `avg_fill_price`, `fees`, and whose order it was:
  `order_source`, `bot_id`, `order_origin`) and its positions at the ledger's mark. Sim off the live
  edge, or with the desk elsewhere, is not counted (`unknown` says so).
- **Live**: IBKR's own -- `ib.fills()` (today's executions, read back at every connect) for the account
  Nova is logged into, and `ib.portfolio(account)` at IBKR's `marketPrice`; stocks only (`secType`
  `STK`). IBKR not READY is an unknown. Every Live fill is yours: a bot never trades Live.

**When it acts** (`loss_limit/watch.py`, every `LOSS_LIMIT_POLL_SEC`, 1 s). Two marks per line that is
set, per account: 80% of the line's limit (`LOSS_LIMIT_WARN_FRACTION`) and the limit. A mark is crossed
only after that line's loss stays at or past it for `LOSS_LIMIT_CONFIRM_SEC` (10 s) in a row; a reading
under it, or an unknown one, starts the wait again. Each mark acts once per account, line and day:

- 80%, with Warn me: `warned_at` / `warned_loss` -- the desk's notice and voice line.
- the limit: `tripped_at` / `tripped_loss` / `limit_usd` -- the desk says it whichever boxes are
  checked (no silent blocks); No new buys reads it; with Auto sell, what the line counts open from today
  is closed (`loss_limit/sell.py`): its working orders cancelled (source `cancel_working`),
  then a protective close through the execution door -- source `flatten`, origin `loss_limit` (the
  Account line) or `loss_limit_you` / `loss_limit_bots` (a side line),
  `target_venue` the account, and `intent: "flatten"` on Live and on the practice account the desk shows (the
  door then holds it to the position less the closes working; a practice account the desk does not show is
  closed for the shares its own ledger holds, as the Live Trader bot's closes are) -- at market on Paper and Sim, and on Live at market
  in regular hours and a marketable limit outside them (`execution.flatten_exit`), up to
  `LOSS_LIMIT_SELL_RETRIES` (3) tries each. `sold: [{symbol, side, qty, ok, order_id, error}]` and
  `sell_error` (the first failure, or null) are written beside the trip. The trip is saved with `sell:
  "pending"` before any order goes out and `"done"` once the closes answered: a sale a restart interrupted
  is taken up again by the next pass that can count the account (it closes only what is still held from
  today), and the desk holds the trip's notice while it reads `pending`. Each close is added to `sold` the
  moment it answers, so a close sent before a restart is kept. One sale per account per pass: a second line
  that trips in the same pass is saved `pending` and sells on the next pass, from a fresh count.

**No new buys** (`loss_limit/gate.py`). While it is checked and a line that holds the order's side
tripped today, the execution door refuses on that account every order that opens or adds -- a BUY that
covers nothing, a SELL that opens a short -- from any non-protective source: `LOSS_LIMIT_NO_NEW_BUYS`
with the line's words, the Account line's "Daily loss limit reached on Paper at 09:32 ET (down $451.03
against your $405 limit): no new buys until 04:00 ET Fri Oct 16. Selling what you hold, covering a
short, cancels, Flatten and KILL still work. To buy again, raise the limit or uncheck No new buys in
Settings > Loss limits." One exception (ADR 068, operator 2026-10-26): an order with `origin: "claude"` on Paper
is not refused here -- Claude's lane has its own daily max loss (-$500, `agent_trader.rules`); its fills still count
in Paper's totals. The bot and stock mode read `stopped(account, actor=...)` / `buys_stopped`
for their side. A bot's own exits -- stops, targets, the flush exit, the time stop, the Live Trader
bot's closes and sell-all -- are never held or replaced; the limit never turns a bot off.

**The setting** -- `loss-limit.json` in the operator cache (owner `loss_limit/settings.py`):

```json
{"schema_version": 2, "limit_usd": 2000, "you_usd": null, "bots_usd": null, "warn": true,
 "no_new_buys": true, "auto_sell": false, "set_at": 1792071300.0}
```

`limit_usd` is the Account line; `you_usd` and `bots_usd` your trades' and the bots' lines, null for no
line. Each is whole dollars, `LOSS_LIMIT_MIN_USD` (10) to `LOSS_LIMIT_MAX_USD` (1,000,000). No file
reads the defaults ($2,000 on the Account line, no You or Bots line; Warn me and No new buys on; Auto
sell off). A `schema_version` 1 file -- `{limit_usd, warn, no_new_buys, auto_sell, set_at}`, ADR 056's
one line -- reads as the Account line with those values unchanged and no You or Bots line; the next save
writes version 2. An unreadable file, an unknown `schema_version` or a value out of its rule reads the
defaults with `error` saying so; the next save writes a fresh file. One save at a time (a lock across read,
change, write and publish), so two saves sent together each keep their change.

**Today's record** -- `loss-limit-state.json` in the operator cache (owner `loss_limit/state.py`):
`{schema_version: 2, day: "YYYY-MM-DD", accounts: {ACCOUNT: {LINE: {warned_at, warned_loss, tripped_at,
tripped_loss, limit_usd, sell, sold, sell_error}}}}` (`sell`: `pending` | `done`, written only with Auto
sell), `ACCOUNT` one of `live` / `paper` / `sim`, `LINE` one of `account` / `you` / `bots`. A version 1
file kept one record per account (`accounts: {ACCOUNT: {warned_at, ...}}`); it reads as each account's
`account` line, so a trip from before the upgrade still holds. A file from an earlier desk day reads
empty. A file Nova cannot read reads empty with `error` set: the watcher counts again within a second
and trips again if the loss is still past the line. Any change to the setting clears today's records
on every account and line.

**On the wire.**

- `GET /api/loss-limit` -> `{schema_version: 2, settings: {limit_usd, you_usd, bots_usd, warn,
  no_new_buys, auto_sell, set_at, source: "operator" | "default", error}, day, until (epoch of the next
  04:00 ET), accounts: {ACCOUNT: {name, counted_at, pnl, loss, unknown, stocks: [{symbol, pnl, shares,
  by: {you: {pnl, shares}, bots: {pnl, shares}}}], held_before: [symbol], costs_unknown, lines: {LINE:
  {on, pnl, loss, warned_at, warned_loss, tripped_at, tripped_loss, limit_usd, sell, sold, sell_error,
  no_new_buys: STOP | null}}, no_new_buys: {you: STOP | null, bots: STOP | null}}}, error, rules:
  {min_usd, max_usd, warn_fraction, confirm_sec}}`. `STOP` is `{account, line, tripped_at, loss,
  limit_usd, until, text}`; `lines[LINE].no_new_buys` is the stop that line holds, `no_new_buys[SIDE]`
  the one that holds that side now (the Account line's first). `on` is false for a side line with no
  dollars; its `pnl` and `loss` are still counted. Version 1 had the Account line's record fields and
  one `no_new_buys` at the top of each account.
- `PUT /api/loss-limit {limit_usd?, you_usd?, bots_usd?, warn?, no_new_buys?, auto_sell?}` saves
  (`you_usd` / `bots_usd` null turns that line off), clears today's records, restarts every 10-second
  wait, and answers the `GET` shape. `400` (`detail` the rule in words, header
  `X-Nova-Reason: LOSS_LIMIT_INVALID`) for a value out of its rule or an unknown key; `503` when the file cannot be written (unchanged).

**On the desk.** Settings > Loss limits (a left-menu entry under Sensors): Daily loss limit ($), Your
trades ($, empty: off), Bots' trades ($, empty: off), then Warn me, No new buys and Auto sell ("sell
what's held") for every line, each with a hover tip in the words above. The desk's notices read
`GET /api/loss-limit` and raise one notice per account, line and day for a warning and for a trip
younger than 10 minutes -- with the voice -- naming the line ("The bots' loss limit reached on Paper."),
the account, the loss against the limit, and what followed (no new buys until 04:00 ET; each stock sold
with its order id, or why not). The voice and the Orders table name a close by its origin: `loss_limit`
"Loss limit", `loss_limit_you` "Loss limit · You" (voice "Your loss limit."), `loss_limit_bots` "Loss
limit · Bots" (voice "Bots' loss limit."); rows from before ADR 056 keep their `bot_trip` / `all_stop` labels.

## Three lines: yours, the bots' and the account's (ADR 063, operator decisions 2026-10-20)

**Whose trade** (`loss_limit/accounts.by_of`, `loss_limit/count.py`). A trade belongs to the side whose
order opened its shares, read from the practice ledger row's own stamps: the bots' when `order_source`
is `bot` or `bot_id` is set (the rule `practice.history`'s by-source split uses), or when `order_origin`
is a bot's own close (`bot`, `bot_api`, `live_trader`, sent as source `flatten`), or `loss_limit_bots`;
yours when `order_origin` is `ticket_flatten` or `loss_limit_you`; one of Nova's own closes (`by` null)
for any other `flatten` / `kill` / `cancel_working` order -- KILL, the day cover, a margin call, the
Account line's Auto sell; yours otherwise (an approved plan, Nova's exit on your shares, the ticket).
Every Live fill is yours.

A stock's fills are read in the order they filled. Each first closes shares held the other way -- its
own side's first, then the other side's; Nova's own close takes from each side in proportion to what it
holds, in whole shares -- and the cash it moves and its share of the commission go to the side whose
shares it closed. What is left opens for the side that sent it (yours for Nova's own close, which never
opens). Each side's P&L is its cash plus its shares at the mark; the two add up to the account's -- in
cents, the Bots figure takes the rounding left over, on each stock and in total, so You + Bots is always the
Account figure on the wire. So
you selling a bot's shares by hand, or Flatten closing them, counts on the Bots line.

**Which line holds whom.** The Account line's trip holds every new buy on the account. The You line's
holds only orders whose source is not `bot`; the Bots line's only source `bot` -- every bot entry,
Auto-entry and the Live Trader bot's steps (`gate.actor_of`). Stock mode asks for `you` before an
approved plan and for `bots` for Auto-entry and Bot.

**Auto sell per line.** The Account line closes every share opened today after cancelling every working
order on those stocks. A side line closes only that side's shares opened today
(`Count.opened_today(line)`) and cancels only that side's working orders there (on Live, every order is
yours); its origin stamps the close with the line, so the count gives the sold shares back to that side.
The Bots line's close never goes to Live (`execution.venue_door`: "a bot never trades Live").

**Constants** (`backend/constants_loss_limit.py`): `LOSS_LIMIT_LINES` (`account`, `you`, `bots`),
`LOSS_LIMIT_LINE_KEYS` (each line's setting key), `LOSS_LIMIT_SIDE_ORIGINS`, `LOSS_LIMIT_BOT_CLOSE_ORIGINS`;
`EXECUTION_ORIGINS` gains `loss_limit_you` and `loss_limit_bots`.
