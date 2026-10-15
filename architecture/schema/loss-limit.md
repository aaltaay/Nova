# Data schema: The daily loss limit

## One daily loss limit (ADR 056, operator decisions 2026-10-15)

One dollar line for every account -- Live, Paper and Sim -- that counts your trades and the bots'
alike. It replaces the bot trip and the all-stop (ADR 032, superseded). Owner: `backend/loss_limit/`.

**What it counts** (`loss_limit/count.py`, pure). Per account, the trades opened today (from 04:00 ET,
`practice.clock`): for each stock with fills today, the cash those fills moved (a buy pays, a sell
receives), less their commissions and fees, plus the shares still held at the account's own mark. A
stock the account already held when the day began -- its shares now less today's net fills is not
zero -- never counts and is never sold, however it was traded today. An open position with no usable
mark makes the figure unknown (`pnl: null`, `unknown` says why); an execution whose commission IBKR
has not reported counts without it (`costs_unknown`, a count of such fills).

- **Paper**, and **Sim while the desk is on Sim at the live edge**: the practice ledger's orders filled
  since its day began (`fill_ts`, `filled_qty`, `avg_fill_price`, `fees`) and its positions at the
  ledger's mark. Sim off the live edge, or with the desk elsewhere, is not counted (`unknown` says so).
- **Live**: IBKR's own -- `ib.fills()` (today's executions, read back at every connect) for the account
  Nova is logged into, and `ib.portfolio(account)` at IBKR's `marketPrice`; stocks only (`secType`
  `STK`). IBKR not READY is an unknown.

**When it acts** (`loss_limit/watch.py`, every `LOSS_LIMIT_POLL_SEC`, 1 s). Two lines per account: 80%
of the limit (`LOSS_LIMIT_WARN_FRACTION`) and the limit. A line is crossed only after the loss stays at
or past it for `LOSS_LIMIT_CONFIRM_SEC` (10 s) in a row; a reading under it, or an unknown one, starts
the wait again. Each line acts once per account per day:

- 80%, with Warn me: `warned_at` / `warned_loss` -- the desk's notice and voice line.
- the limit: `tripped_at` / `tripped_loss` / `limit_usd` -- the desk says it whichever boxes are
  checked (no silent blocks); No new buys reads it; with Auto sell, every stock the count holds open
  from today is closed (`loss_limit/sell.py`): its working orders cancelled (source `cancel_working`),
  then a protective close through the execution door -- source `flatten`, origin `loss_limit`,
  `target_venue` the account, and `intent: "flatten"` on Live and on the practice account the desk shows (the
  door then holds it to the position less the closes working; a practice account the desk does not show is
  closed for the shares its own ledger holds, as the Live Trader bot's closes are) -- at market on Paper and Sim, and on Live at market
  in regular hours and a marketable limit outside them (`execution.flatten_exit`), up to
  `LOSS_LIMIT_SELL_RETRIES` (3) tries each. `sold: [{symbol, side, qty, ok, order_id, error}]` and
  `sell_error` (the first failure, or null) are written beside the trip. The trip is saved with `sell:
  "pending"` before any order goes out and `"done"` once the closes answered: a sale a restart interrupted
  is taken up again by the next pass that can count the account (it closes only what is still held from
  today), and the desk holds the trip's notice while it reads `pending`. Each close is added to `sold` the
  moment it answers, so a close sent before a restart is kept.

**No new buys** (`loss_limit/gate.py`). While it is checked and an account tripped today, the execution
door refuses on that account every order that opens or adds -- a BUY that covers nothing, a SELL that
opens a short -- from any non-protective source, yours and the bots': `LOSS_LIMIT_NO_NEW_BUYS` with
the words "Daily loss limit reached on Paper at 09:32 ET (down $451.03 against your $405 limit): no new
buys until 04:00 ET Fri Oct 16. Selling what you hold, covering a short, cancels, Flatten and KILL still
work. To buy again, raise the limit or uncheck No new buys in Settings > Loss limits." The bot and stock
mode read `buys_stopped(account)`. A bot's own exits -- stops, targets, the flush exit, the time stop,
the Live Trader bot's closes and sell-all -- are never held or replaced; the limit never turns a bot off.

**The setting** -- `loss-limit.json` in the operator cache (owner `loss_limit/settings.py`):

```json
{"schema_version": 1, "limit_usd": 2000, "warn": true, "no_new_buys": true, "auto_sell": false,
 "set_at": 1792071300.0}
```

`limit_usd` is whole dollars, `LOSS_LIMIT_MIN_USD` (10) to `LOSS_LIMIT_MAX_USD` (1,000,000). No file
reads the defaults ($2,000; Warn me and No new buys on; Auto sell off). An unreadable file, an unknown
`schema_version` or a value out of its rule reads the defaults with `error` saying so; the next save
writes a fresh file.

**Today's record** -- `loss-limit-state.json` in the operator cache (owner `loss_limit/state.py`):
`{schema_version: 1, day: "YYYY-MM-DD", accounts: {ACCOUNT: {warned_at, warned_loss, tripped_at,
tripped_loss, limit_usd, sell, sold, sell_error}}}` (`sell`: `pending` | `done`, written only with Auto sell), `ACCOUNT` one of `live` / `paper` / `sim`. A file from
an earlier desk day reads empty. A file Nova cannot read reads empty with `error` set: the watcher
counts again within a second and trips again if the loss is still past the line. Any change to the
setting clears today's records on every account.

**On the wire.**

- `GET /api/loss-limit` -> `{schema_version: 1, settings: {limit_usd, warn, no_new_buys, auto_sell,
  set_at, source: "operator" | "default", error}, day, until (epoch of the next 04:00 ET), accounts:
  {ACCOUNT: {name, counted_at, pnl, loss, unknown, stocks: [{symbol, pnl, shares}], held_before:
  [symbol], costs_unknown, warned_at, warned_loss, tripped_at, tripped_loss, limit_usd, sell, sold,
  sell_error, no_new_buys: {account, tripped_at, loss, limit_usd, until, text} | null}}, error, rules:
  {min_usd, max_usd, warn_fraction, confirm_sec}}`.
- `PUT /api/loss-limit {limit_usd?, warn?, no_new_buys?, auto_sell?}` saves, clears today's records,
  restarts every 10-second wait, and answers the `GET` shape. `400` (`detail` the rule in words, header
  `X-Nova-Reason: LOSS_LIMIT_INVALID`) for a value out of its rule or an unknown key; `503` when the file cannot be written (unchanged).

**On the desk.** Settings > Loss limits (a left-menu entry under Sensors): Daily loss limit ($), Warn
me, No new buys, Auto sell ("sell what's held"), each with a hover tip in the words above. The desk's
notices read `GET /api/loss-limit` and raise one notice per account and day for a warning and for a
trip younger than 10 minutes -- with the voice -- naming the account, the loss against the limit, and
what followed (no new buys until 04:00 ET; each stock sold with its order id, or why not). The voice
and the Orders table name a close with origin `loss_limit` "Loss limit"; rows from before ADR 056 keep
their `bot_trip` / `all_stop` labels.
