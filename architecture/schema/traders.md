# Data schema: The three traders

Part of `AGENTS.md` §3 (Data Schema). Owners: `backend/owners/` (books and rules) and `backend/traders/` (the On / Off
switches and the limits). Same law as the constitution: a wire or persisted shape changes here first, in the same
commit as the code (Invariants #1 and #5).

## Three traders: you, Claude, the brain (ADR 072, operator decisions 2026-11-13)

**Confirmed for the build; built batch by batch** (ADR 072 "Build order"). Until a batch lands, the sections it
replaces still describe the desk: `recording-and-replay.md` "Your book and the bots' book", `loss-limit.md` "Three
lines", `agent-trader.md` (Stop Claude, Take Claude's line, the -$500 in code) and `bot.md` (the Bots page, the Live
Trader). Each batch's PR rewrites what it replaces in the same commit.

**The owners.** `owner` is one of `you`, `claude`, `brain` or `earlier_bots`, on Paper and Sim; on Live every row is
`you`. `bot` is set only on `earlier_bots` rows and names the retired holder: `bot` (the strategy bot), `auto_entry`,
`bot_api`, `live_trader`. Constants: `constants_owners.OWNERS` (`you`, `claude`, `brain`), `OWNER_EARLIER_BOTS`,
`EARLIER_BOT_HOLDERS`, `OWNER_NAMES` ("You", "Claude", "The brain", "Earlier bots").

**Whose an order is** (`owners.whose.by_of`, pure, from the practice ledger row's own stamps -- never its side, size
or time), in this order:

1. `order_origin` `claude` or `loss_limit_claude`: `claude`.
2. `order_origin` `brain` or `loss_limit_brain`: `brain`.
3. `order_source` `bot`, a `bot_id`, or `order_origin` one of `bot`, `auto_entry`, `bot_api`, `live_trader`,
   `close_bots`, `loss_limit_bots`: `earlier_bots` (`bot` the origin when it names a holder, else `bot`).
4. `order_origin` `ticket_flatten` or `loss_limit_you`: `you`.
5. Any other source `flatten`, `kill` or `cancel_working`: none -- one of Nova's own closes (KILL, the day cover, a
   margin call, the Account line's Auto sell, a lapsed lease, a flat-by close). It closes each holder's own shares,
   in proportion where more than one holds (`owners.split`).
6. Everything else: `you`.

Every share is booked at its holder's own average cost (`owners.holdings`), and the holders add up to the account to
the cent (the last holder takes the rounding). A practice ledger written before ADR 072 reads with the same rule, so
Claude's past fills are Claude's and every other bot's are Earlier bots'. Nothing is rewritten.

**A trader's stock.** A stock is a trader's while that trader holds shares in it or has an order with `effect:
"opens"` working there (`owners.rules.stock_of(symbol) -> owner | null`). Earlier bots' shares at the upgrade are
handed to you on the first read (below), so `earlier_bots` never owns a stock.

**The rules at the door** (`owners.rules`, asked by `execution.practice_checks` and again by the practice broker at
placement and at the fill, on Paper and Sim; a refusal at the fill cancels the order with the same words):

| Code | When | Words (example) |
|---|---|---|
| `OWNERS_TRADERS_STOCK` | An order that opens or adds (a BUY that covers nothing, a SELL that opens a short), from any trader, on a stock another trader owns | "XLAB is the brain's: nobody adds to another trader's stock." |
| `OWNERS_TRADER_ON` | Any order of yours (Buy, Sell, Cover, Flatten, the exit pair) on a stock Claude or the brain owns while its switch is On, unless the position there is handed to you | "XLAB is the brain's. Switch the brain off to close it yourself." |
| `OWNERS_BUDGET` | A trader's entry that would pass its budget (open shares at the mark plus working entries at their limit, this entry counted once at its price) | "The brain skipped SOFI: its $25,000 would be passed ($23,400 held + $2,500)." |
| `OWNERS_NOT_YOURS` | A close past its sender's own shares (for you: your own plus handed shares) | "You hold no SPCX; the 51 are Claude's, and Claude is On." |
| `OWNERS_OTHER_SIDE` | An order that would leave one holder long and another short (kept as a guard) | "Buy SPCX refused: Claude is short 51. One account can't be long and short the same stock." |

Your cancels, KILL, Freeze all orders and Nova's own closes are never refused here. Retired:
`OWNERS_BOT_STAYS_OUT`, `OWNERS_BOTS_BUDGET`, `OWNERS_NOTHING_TO_CLOSE`.

**Handed to you and closed by you.** Turning Claude's or the brain's switch Off hands every position it holds then:
`by_owner[].handed: true`. A handed position stays handed until that trader is flat in the stock, whatever the
switch does after (the operator, 2026-11-13): the trader may not open, add or close there (`OWNERS_TRADERS_STOCK`;
its own resting exits still fill). The marks are kept in `trader-handed.json` in the operator cache, rewritten whole
and atomically: `{schema_version: 1, handed: [{venue: "paper" | "sim", trader, symbol, at}]}`. An entry ends when the
trader's shares there are flat on that venue; a Sim entry also ends when the Sim account resets or a rewind goes back
before `at`. A missing or unreadable file reads empty and is logged; it is never guessed from the switches. Your Sell, Cover, Flatten and the exit pair size from your own shares plus handed shares
(`GET /api/ibkr/positions` on Paper and Sim adds `handed_qty` and `handed_from`). A close that reaches handed shares
first cancels that trader's resting exits in the stock (source `cancel_working`, origin `takeover`), then sells your
own shares and then the handed ones. Each part of a fill that closes handed shares is booked on that trader's book
with `closed_by: "you"` (`fills[].parts[].closed_by`, and `fills[].closed_by` when any part has it). You never add to
a handed position (`OWNERS_TRADERS_STOCK`). A retired bot's shares still open at the upgrade read as handed from
`earlier_bots`.

**The switches** (`backend/traders/switches.py`). One per AI trader: `claude`, `brain`.

- File `trader-switches.json` in the operator cache, rewritten whole and atomically:
  `{schema_version: 1, day: "YYYY-MM-DD", switches: {claude: {on, at, by}, brain: {on, at, by}}}`. A file from an
  earlier desk day, a missing one, an unknown `schema_version` or an unreadable one reads every switch Off (with
  `error` saying why for the last two). The 04:00 ET rollover writes every switch Off. A restart within the day reads
  the file back, so a restart never hands a trade over by itself.
- **On** is refused `409` with `{reason, error}`: `TRADER_LIVE` (the desk is on Live), `TRADER_DAY_STOP` (the
  trader's loss line tripped today, decision 8), `TRADER_PAST_FLAT_BY` (at or after its flat-by time),
  `TRADER_OPERATOR_ONLY` (a request carrying `X-Agent-Seat`, or the brain's session key), `REMOTE_VIEW_ONLY` (the
  phone, ADR 070).
- **Off** is never refused. It writes the file first, then cancels the trader's unfilled entries (source
  `cancel_working`, origin `takeover`), Claude's armed breaks and reflexes; its exit legs keep resting; Claude's guard
  skips the stock. Each step is an event on the trader's stream (`switch_off`, `handed`: "The brain is off: its 200
  XLAB are yours to close. Its stop at 4.19 keeps resting.").

**The limits** (`backend/traders/limits.py`). File `trader-limits.json` in the operator cache, rewritten whole and
atomically: `{schema_version: 1, traders: {claude: {max_shares, risk_usd, budget_usd, flat_by}, brain: {...}},
set_at}`. `max_shares` whole shares 1 to 10,000; `risk_usd` whole dollars 1 to 10,000 (the most between entry and
stop); `budget_usd` whole dollars 100 to 1,000,000; `flat_by` `"HH:MM"` ET from 09:30 to 15:55. Defaults (no file,
or a trader missing from it): 1,000, 150, 25,000, `"15:55"` -- Claude's code values before ADR 072
(`AGENT_MAX_SHARES`, `AGENT_MAX_RISK_USD`, `AGENT_CLOSE_ET`). An unknown version or unreadable file reads the
defaults with `error`; the next save writes a fresh file. A trader's daily loss limit is its loss line
(`loss-limit.md`, "Four lines"), not in this file.

**On the wire** (`backend/traders/routes.py`, loopback only; writes need the desk's API key):

- `GET /api/traders` -> `{schema_version: 1, generated_at, venue, traders: {claude: TRADER, brain: TRADER}, error}`.
  `TRADER` is `{name, on, at, can_turn_on, why_not_on, done_for_today, state, text, symbol, lane: {symbol, depth,
  tape}, position: {symbol, qty, avg_cost, mark, unrealized_pnl} | null, handed: [{symbol, qty, stop_price}], today:
  {pnl, loss_limit_usd, tripped_at}, limits: {max_shares, risk_usd, budget_usd, budget_used_usd, flat_by}, note:
  {text, at} | null}`. `state` is one of `off`, `watching`, `buy_set`, `in_trade`, `done`; `text` is the pill's words
  ("Brain · In XLAB +$42.00", "Brain · Off · XLAB is yours to close", "Brain · Done for today -$500"). Claude's
  `state`, `symbol`, `note` and position are the seat's (`agent-trader.md`); the brain's are its door's.
- `PUT /api/traders/{trader}/switch {on: boolean}` -> the `GET` shape, or the refusal above. `404 TRADER_UNKNOWN`
  for another name.
- `PUT /api/traders/{trader}/limits {max_shares?, risk_usd?, budget_usd?, flat_by?}` -> the `GET` shape. `400
  TRADER_LIMITS_INVALID` with the rule in words for a value out of its rule or an unknown key; `503` when the file
  cannot be written.

**On the desk** (mockup `F:\Nova\design\brain-switches\v1`): the header carries Claude's pill and the brain's twin,
each with its switch; the words open the trader's panel (lane, position, today against the day stop, limits with a
link to Settings, and for the brain what it is reading now). Settings > Loss limits has one column per trader:
daily loss limit, max shares, risk a trade, budget, flat by; your column shows the You loss line and your own order
size limit (`execution.md`, ADR 064) with budget and flat by not applying. Every split reads All / You / Claude /
The brain / Earlier bots.

**Live.** On Live every fill is yours, no switch turns On, and `execution.venue_door` refuses any `claude` or `brain`
send to Live in words. Nothing here changes arming, `auto_live` (NO-GO) or Invariant #7.
