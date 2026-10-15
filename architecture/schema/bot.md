# Data schema: The bot, its playbook and the Bots page

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/bot/, backend/hot_list/, backend/line_lending/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Bot playbook and the read-out gate (ADR 027, operator decision 2026-09-23)

The bot packs (halt-luld, quote-spike, volume, llm-decide), `POST
/api/bot/llm/spend` and the `nova-brain` sidecar are retired. The bot session
file is `schema_version: 5` (ADR 042); a v1-4 file migrates on load (v1-3:
`active_pack`, `pack_settings` and `llm` stripped; v4: below) and an unknown
version refuses loudly. **One owner for Nova's buys (ADR 042, operator decision
2026-09-30: "why is it a radio button? We are already choosing if it's off,
eyes only, or strategy independently in each strategy").** There is no chosen
setup: the session's `level` (per venue, "The level belongs to a venue" below)
is the **master ceiling** -- the most any setup may do on this venue, and the
level the localhost bot API reads -- and `setup_levels: {SETUP: 0 | 1 | 2}`
holds every setup with a scanner's own level; a setup's **effective** level is
the lower of the two. Off (0) watches and scores in silence, Eyes (1) proposes,
Strategy (2) lets Nova's bot and Auto-entry trade its go triggers while the bot
is Active (until then it proposes like Eyes). `GET /api/bot/session` adds
`setups: [{id, scanner, level, effective}]` (`level` / `effective` null without
a scanner) and `setup_levels`; `PATCH /api/bot/session {setup_levels: {SETUP:
0 | 1 | 2}}` sets any of them (each change a `setup_level` audit line `inputs:
{setup, from, to}`), and raising the master `level` needs no Activate token
(configuration is not "go"). `PATCH {setup}` is refused `400
BOT_SETUP_RETIRED`. The v4 -> v5 migration gives the old chosen setup the old
`level`, keeps the others' 0 / 1, drops `setup`, `strategy` and the `advise`
budget (and `/api/bot/advise*`, which nothing called), and moves the sleeve, the
bot list and the day lock into each venue's dial (below). A watch-only setup (#847,
the pullback dip; setups.md "The pullback dip: a watch-only setup") is never
Strategy: `PATCH` refuses its 2 with 409 `BOT_SETUP_WATCH_ONLY`, an older 2 reads
as Eyes in `effective`, and its `setups[]` entry adds `watch_only: true` and
`locked` (why); its Eyes draws and never proposes.

`readout` (owner `setup_scanner/readout.py`, cached 30 s) is `{state:
"collecting" | "passed" | "not_passed" | "failed" | "unavailable", passed,
reason, go: {triggered, scored, win_pct, avg_net_r}, control: {...}, rules:
{kind, min_go, fail_go, min_net_r}}` over every `setups.db` row of the setup's
first-of-the-day kind (`rules.kind`: `first_pullback`, `bull_flag`,
`flat_top_breakout` or `red_to_green`, ADR 031) that triggered: `go` are those whose tape was go at the
trigger, `control` those blind or wait (pooled). It passes when at least 50 go
setups triggered and their average net R is above +0.2 and above the
control's; it is judged on the first 100 go setups, and 100 without a pass is
`failed`. A closed store is `unavailable`. **Read-outs are evidence, and
gate nothing** (ADR 042, amending ADR 027 / 030): Nova's bot trades Paper and
Sim only, and Live trading by a bot is not built -- it waits on its own operator
decision -- so passing a read-out unlocks nothing yet. Each setup's card shows
its own read-out (`GET /api/setups/templates`). Since #845 (operator decisions 2026-10-09 and 2026-10-12;
setups.md, "Targets replace 2R") the read-out scores the bot's exit -- `target1_fraction` of the shares at
target 1, the rest at target 2, the stop staying where it is after the first part, the bailout -- no longer the
backtest's (half at target 1, break-even, a 9 EMA trail). A trigger hands the bot `target1`, `target2` (or
null) and `target1_fraction` on its setup; the bot's two-half bracket that sells them is the order side (#681). The session's
`readout`, `readout_required` and the `readout` gate are gone. **The localhost
bot API refuses Live**: every `POST /api/bot/action` on Live or on a replay desk
is refused `409 BOT_LIVE_NOT_BUILT`, exits and cancels included (a bot never
touches Live). At Strategy a `buy_*` kind is also refused outside its setup's
bot window on the venue's clock (each setup's template in play: `409
BOT_OUTSIDE_WINDOW`), outside 09:30-16:00 ET while the venue's sleeve turns
extended hours off, and past the venue's daily cap (`409 BOT_DAY_TRADE_CAP`):
the sleeve's `entries_per_day` (1-3, default 1) counts Nova's automatic entries
-- the bot's and Auto-entry's together -- per venue day, from the persisted audit
stream (entry audit rows carry `inputs.venue_day`; an entry cancelled unfilled
-- a `missed` -- gives the day back; Approve is counted, `entries_today.approved`,
never capped); exits and cancels are never held by either. **Commissions unknown
hold new entries** (operator decision on #564, 2026-09-24): while the session's
commission read fails, every bot entry on Live -- a `buy_*` kind on `POST
/api/bot/action` and the bot's own entry (both pass
`entry_rules.assert_entry_allowed`) -- is refused `409
BOT_COMMISSIONS_UNKNOWN` until a read succeeds again (the unreadable file is the
execution ledger every order is written to). Exits, cancels, flatten and kill
are never held, and Paper and Sim never are; a venue that cannot be read counts
as Live. The failure is logged (at once, then at most every
`BOT_COMMISSIONS_WARN_EVERY_SEC`), never read as $0. **The breakers compare
IBKR's own figure** (ADR 042 / #664): on Live, the finite `dailyPnL` from
`reqPnL` for the current READY IB instance, generation and account. IBKR owns
that figure's reset (the TWS configuration, not Nova's 04:00 ET lock boundary);
the API supplies no reset timestamp, so the meter never invents one. Pending,
failed, disconnected or superseded subscriptions cannot supply cached daily
P&L. While it is unavailable, the stated fallback is `RealizedPnL + UnrealizedPnL`,
which can include an overnight position's lifetime move. Both broker figures
already include commissions (TWS Users' Guide, Profit and Loss) -- until
2026-09-30 the breakers subtracted the session's commissions again and tripped
that many dollars early; on Paper and Sim at the live edge, the practice
ledger's `DayPnL`; on a replay desk nothing (a replay's P&L is not today's).
`GET /api/bot/pnl`'s meter says which: `{compares, source, venue, compared,
note, error, day_pnl, commissions, commissions_in_figure, commissions_unknown,
commissions_error, fallback, fallback_reason, reset_semantics, reset_time,
daily_pnl_updated_at, ...}`. The fallback and its limitation are visible; no
session commission is subtracted again. A commission read failure still holds
new Live bot entries without invalidating the known P&L. Practice day boundaries,
breaker thresholds, existing latches and trading authorization are unchanged.
Proposals are accepted at Eyes and Strategy. **Every gate is drawn with its
reason** (owner `bot/gates.py`): `gates: [{id, ok, stage: "activate" | "fire",
detail: {..., text}}]` are `venue` (Paper, or Sim at its live edge), `level`
(the master at Strategy), `setups` (`at_strategy`), `padlock`, `allowlist`
(stocks set to Bot or to Auto-entry on this venue; stage `fire`, so it never
locks Activate -- Auto-entry needs the bot Active), `depth_lines` (ok while at
least one Bot stock holds a depth line, `held`, `missing`, `max_lines`; each
trigger still needs its own), `bot_trip`, `day_lock`, `kill_switch`, `window`
(per Strategy setup: `setups: [{setup, start, end, open, clipped, error}]`),
`daily_cap` (`count`, `cap`, `venue_day`), `extended_hours` and `commissions`;
the session adds `ready` / `ready_reason` (the bot would trade a go trigger now)
with `live_fire_ready` as a one-release alias.

**Activate: one control, one meaning, never carried** (ADR 042, owner
`bot/activation.py`). `POST /api/bot/session/arm {reenable?}` refuses, `409`
with a plain reason: `BOT_LIVE_NOT_BUILT` (Live), `BOT_REPLAY_DESK` (Sim off the
live edge with nothing loaded; a loaded replay is traded, ADR 052), `BOT_VENUE_UNKNOWN`, `BOT_LEVEL_NOT_STRATEGY`,
`BOT_NO_SETUP_AT_STRATEGY`, `BOT_PADLOCK_LOCKED` and `BOT_TRIP_LATCHED` (the
bot trip fired on this venue today; the desk confirms in words, then sends
`reenable: true`). Choosing Strategy never activates. The backend clears
Activate -- a `deactivate` audit line and `deactivated: {at, reason, text}`,
`reason` one of `restart | padlock | venue | level | no_setup | bot_trip |
all_stop | operator` -- on every process start (like spend arming, ADR 018),
when anyone locks the padlock (`ibkr.safety.set_armed` calls
`activation.on_disarm`; it used to be only a page effect), on a venue change,
with the master below Strategy or no setup left at Strategy, and on a trip. The
session's `active` is the truth (`armed` a one-release alias; `has_desk_arm`,
the token's presence, stays).

**One sleeve per venue** (ADR 042, owner `bot/sleeve.py`, #658 item 2). Each
venue's dial carries its own `caps: {venue, risk_usd, max_shares,
bp_budget_usd, working_ttl_sec, extended_hours, entries_per_day, api_kinds}`
(`allowlist`, the localhost API's order kinds, a one-release alias of
`api_kinds`); bounds `caps_bounds` (risk 1-10,000, shares 1-10, budget up to
$50, TTL 1-10 s, entries 1-3); a value out of bounds is refused `400
BOT_CAPS_INVALID`, never clamped in silence. `PATCH {caps: {venue?, ...}}`
edits the named venue's (else the desk's); `caps_by_venue` lists all three. The
migration copied the one sleeve to every venue. **One size**
(`bot/sizing.py`, pure) for every Nova automatic buy: floor(`risk_usd` / the
setup's risk a share), capped by `max_shares` and by what the budget still buys
(`{qty, by_risk, capped_by: "max_shares" | "budget" | null, text}`; under one
share is a stated skip). `risk_usd` is also the Trader's risk per trade. **One
entry timeout**: `working_ttl_sec` for the bot, Auto-entry and Approve.
`extended_hours` (default on: the default bot windows open at 07:00 ET) binds
the bot and Auto-entry. `entries_today: {count, cap, venue_day, entries:
[{symbol, setup_type, by, ts, outcome}], approved, error?}`.

**Loss breakers per venue** (ADR 032, operator ask 2026-09-24). The bot trip
(soft: flatten, the bot to L0) and the all-stop (hard: flatten, bot and manual
buys on that venue locked until the next 04:00 ET -- ADR 042: the practice
day's own boundary; at midnight they had lifted while the practice day's P&L
still read yesterday's loss, and tripped again) compare the whole account's day P&L with
the desk venue's own thresholds (owner `bot/breaker_limits.py`): the session
keeps `breakers: {VENUE: {soft_usd, hard_usd}}` for `live` / `paper` / `sim`
(an optional key of schema 4; a venue with none reads -50 / -200; a venue Nova
cannot read reads Live's). `GET /api/bot/session` adds `breakers: {venue,
soft_usd, hard_usd, custom, defaults: {soft_usd, hard_usd}, by_venue: {VENUE:
{soft_usd, hard_usd}}, bounds: {soft_usd: [loosest, tightest], hard_usd:
[loosest, tightest], step_usd}}`; `PATCH /api/bot/session {breakers: {venue?,
soft_usd?, hard_usd?}}` changes the named venue (else the desk's) within -5 to
-1,000 (bot trip) and -10 to -5,000 (all-stop), the bot trip above the
all-stop, snapped to $5 -- `400 BOT_BREAKER_INVALID` otherwise -- and records a
`breakers` audit line; a venue moved back onto -50 / -200 keeps no pair of its
own (`custom: false`). Moving a threshold never clears a fired bot trip or a
day lock. A trip writes its record on the dial of the venue whose P&L tripped:
`hard_lock_until_date` (an ISO datetime of the next 04:00 ET; a legacy
`YYYY-MM-DD` still lifts at that date's 00:00 ET), `hard_lock_at`,
`hard_lock_pnl`, `hard_lock_usd`, and the bot trip's `soft_breaker_at`,
`soft_breaker_pnl`, `soft_breaker_usd`; `bot.buy_lock.lock_for(row, venue)` reads
any venue's, `execution.service` asks with the door's own venue, and the session
adds `day_lock: {active, until, tripped_at, pnl, venue, threshold, text}`,
`day_locks` and `soft_breaker: {fired, at, pnl, until}` (`hard_lock_until_date`
/ `day_lock_active` stay one release, the desk venue's). On a replay desk the
breakers compare nothing and `breakers.note` says so. The Bots page drags the two markers on the desk venue's bar (it asks
before loosening Live), and the Account page's Risk block reads the same pair. A trip's flatten carries
its origin (`bot_trip` / `all_stop`, "Who sent it" under the execution command), and its audit line
(`breaker_soft` / `breaker_hard`) adds `inputs.closes: [{symbol, side, qty, ok, order_id, error, opened_by}]`
(what the flatten sold, one line per position) and `inputs.flatten_error`. `opened_by` (2026-10-14, ADR 045
amendment) is the newest filled order on the other side of that close on the trip's venue, from the execution
record (`bot.flatten.opened_by`): `{order_id, source, side, qty, order_type, price (the order's own limit or
stop, never a guessed fill), placed_ts, filled_ts} | null`; the notice adds "It came from your order 255: Buy
1,000 GENK LMT 2.76, placed 09:25:19 ET, filled 09:28:26 ET." under the close. **Every desk window says so**
(operator report 2026-10-01: the trip had been visible only on the Bots and Account pages): the bot's
notices (`frontend/src/bot/breakerNotices.ts`) read the polled audit stream and raise one notice per trip
younger than 10 minutes -- "Bot trip sold your positions", the venue, the day P&L against the limit, the
time, each position sold with its order id (or why it was not), and what follows -- which stays until it
is dismissed; a failed sell reads "the sell failed -- close your positions yourself". `bot-session.json` and `bot-proposals.json` are written through a
temp file and a rename.

**The level belongs to a venue** (operator report 2026-09-30: "When I switch
between L0 and L2 in the paper, it stays persistent when I switch to live, and
I feel like that shouldn't happen"; owner `bot/venue_levels.py`). Each venue
keeps its own dial -- `level`, `setup_levels`, the bot trip's latch and record,
the all-stop's day lock (ADR 042, #658 option b: Live's lock follows Live and
switching away and back does not escape it), the sleeve (`caps`), the bot list
(`symbol_allowlist`; Live's starts empty: Nova never buys on Live) and the bot's
`working` orders and `bot_qty` -- the session's fields being the dial of
the venue in `level_venue` and the others waiting in `venue_levels: {VENUE:
dial}` (optional keys of schema 4; a venue with none starts Off, its bot trip
clear). `sim.mode.set_venue` puts the old venue's dial away, takes the new
one's and deactivates the bot (a `venue` audit line): Activate never carries
into another venue, like spend arming. A session loaded on another venue than
its `level_venue` takes that venue's dial; one without the stamp belongs to the
venue the desk showed. `GET /api/bot/session` adds `level_venue` and
`levels_by_venue: {live, paper, sim}`. The bot trip's latch adds
`soft_breaker_until` and lapses at the next 04:00 ET like the day lock
(`bot.clock.soft_latched`; a latch without it has lapsed), and the all-stop
trips again once an earlier day's lock has lifted -- it read the stale date as
"locked" and never tripped a second time. Leaving a venue first cancels Nova's
working entries there ("Who trades the stock" below). Every bot audit line
carries `venue`, and the daily entry cap counts this
venue's entries (a line without it counts on every venue). A TTL cancel and a
take-over of the exit never send another venue's order id.

**Nova's own bot** (ADR 030, owner `bot/first_pullback/`; #514; ADR 042; both sides since ADR 049's
step 5, "The bot trades both sides" below: a short strategy's trigger is a short, mirrored).
Active at Strategy, on Paper or on Sim -- at the live edge, or on a loaded replay ("The bot trades a Sim
replay" below) -- never on Live -- it hears the setup scanner's triggers (each setup's template in play's
lane: `SetupEngine.add_trigger_listener`, and the Sim eyes' on a replay; the event carries `setup_type`,
`grade`, `pillars`, `filtered` and `spread`) and plays **every setup at
effective Strategy** on this venue's Bot stocks: the first go trigger wins, one
trade at a time, then the shared daily cap. It takes the first of a setup on a
symbol that day (its kind without `second_`) with the tape at go and the plan a
trade (NOT A TRADE is one rule, below), after every gate (`admit.for_bot`): the
venue, Activate, the setup's level and window, extended hours, a held depth
line, the padlock, the kill switch, this venue's day lock and bot trip, the
working block, the sleeve's size and the daily cap; a trigger it does not take
is a `bot_trade` `skipped` line with every reason (`inputs.codes` /
`reasons`) and the stock's last event on its Trader tab. Its entry is a
**practice bracket** (`operation: "bracket"`, source `bot`: a BUY limit at the
scanner's entry, a SELL limit at target 1 and a SELL stop, the exits held until
the entry fills, then one-cancels-other), so its stop and target rest at the
broker and Paper's fill while the desk shows another venue. **Two halves** (#681,
operator ask 2026-10-12): a setup row with a `target2` (#845) adds a SELL limit at
target 2 -- target 1 sells `target1_fraction` of the shares (half by default, the
smaller part of an odd count; `target1_qty` on the command), target 2 the rest --
and the stop covers every share, shrinking at the broker as the targets fill and
never moved to the entry (`execution.md`, "The exit-only pair and two halves").
A null `target2`, or one share, sells everything at target 1 as before. A first
half that fills is a `bot_trade` `half` line ("sold 2 at target 1 10.3; the stop
9.89 stays for the other 2") and the stock's last event; the trade's `qty` is then
the shares it still holds. The time stop, the flush exit, a take-over and a stop
leg that is gone close whatever is left. A short is the mirror (BUY limits under
its entry). Each leg has its own order id; the entry's idempotency key (with the
replay's run tag on a Sim replay, ADR 052) covers the one bracket (a Sim trade waits while the desk is
elsewhere -- a replay's while the desk is not on the replay it was made on -- and says so). Unfilled after the sleeve's `working_ttl_sec` the entry is cancelled with
its exits (a miss). The time stop (`BOT_FP_TIME_STOP_MIN`, 15 minutes), the
flush exit (a tightened stop is a replace of the stop leg) and a stop leg that is
gone (the bot then watches the stop on IBKR's Last) cancel both legs and sell at
the bid, then the protective flatten. Every order carries its real setup
(`setup=<setup_type>`). It claims the L2 session as brain `nova-first-pullback`
(the id kept from ADR 030) and heartbeats while it plays. `GET
/api/bot/session` adds `runner: {brain_id, playing, reason}` and `trade` -- the
current or last trade, `{setup_id, setup_type, symbol, venue, venue_day,
template_id, template_rev, state: "entering" | "open" | "exiting" | "closed" |
"missed" | "handed" | "rewound", replay_key, qty, trigger, entry_planned, stop, target1, risk,
target2, target1_fraction, entry_qty, entry_order_id, entry_fill_price, entry_filled_ts, target_order_id,
target2_order_id, stop_order_id, stop_leg_at, exit_order_id, exit_price, exit_reason: "target" |
"stop" | "time" | "flush" | "outside" | "handed" | null, halves: [{leg: "target1" | "target2" | "stop" |
"time" | "flush" | "outside" | "handed", qty, price, ts, order_id}], closed_ts, slippage, r,
size_text, waiting, note}` (`r` gross in the setup's risk; with two halves `exit_price` is the
shares-weighted price of every sale in `halves` and `r` counts every share -- the `closed` line's
`inputs.halves` carries the sales, so the day's readout counts both halves; a sale whose price is unknown
leaves both null, as `outside` always did; the day P&L is the venue ledger's and counts every fill), kept in
`bot-session.json` so a restart resumes it; a take-over whose cancel is refused
keeps the trade and says the order still rests. Every step is on the bot audit stream as `bot_trade` (`skipped` |
`missed` | `filled` | `closing` | `closed` | `note` | `error`, `inputs` with
the `setup_id`). A bot working order the bot cancels itself carries
`expire_ts: null` in `working`.

## One Bots page (ADR 044, operator decisions 2026-10-01)

"I definitely don't like it if we have redundancies ... put everything on one page", after AISP's three
triggers went unbought for five reasons no screen showed together. ADR 044 amends ADR 042, 037, 041,
036, 032 and 023 as below.

**The Bot switch.** One per venue, on the desk in place of the master dial and Activate. `POST
/api/bot/session/switch {on: boolean, reenable?: boolean}` (API key) answers the session view.
- **ON** puts the venue's master `level` at Strategy (2) and activates. It is refused like Activate:
  409 `BOT_LIVE_NOT_BUILT`, `BOT_REPLAY_DESK`, `BOT_VENUE_UNKNOWN`, `BOT_NO_SETUP_AT_STRATEGY` (no
  strategy is On), and `BOT_TRIP_LATCHED` unless `reenable`. A successful ON returns `desk_arm_token`,
  as `/arm` does.
- **ON unlocks the padlock** (ADR 044 amendment, 2026-10-12). Once every other rule passes, ON arms the
  desk through the padlock's one rule, `ibkr.safety.arm(True, actor="operator")` (ADR 018), so it
  follows the padlock's rule by venue: where the padlock unlocks without the PIN (Paper, Sim) the press
  unlocks it; where it needs the PIN (`arm_requires_pin`, Live) ON is refused `BOT_PADLOCK_LOCKED`
  until the operator unlocks it with the PIN, and `why_off` names the padlock only there. A refused ON
  never unlocks. An unlocked desk that still cannot place (`places_allowed`) refuses
  `BOT_PADLOCK_LOCKED` with its reason. The `bot_switch` line's `reason` adds "(it unlocked the
  padlock)" when this press unlocked it. OFF leaves the padlock as it is; locking the padlock still
  turns the bot off (`activation.on_disarm`).
- **OFF** deactivates (`deactivated.reason: "operator"`) and puts the master at Eyes (1), so setups
  at Eyes or On still propose.
- **The bot trip** (`bot/autonomy.drop_to_eyes`, `drop_to_l0` kept as its alias) also leaves the master at
  Eyes (1), not Off; its `breaker_soft` line's outcome reads `eyes`.
- Each change is a `bot_switch` audit line, outcome `on` | `off`, `inputs: {on, from_level, to_level}`.
- The session view adds `bot_on: boolean` (active with the master at Strategy) and `switch: {on, venue,
  why_off: string | null, latched: {at, pnl, until} | null}`.
- The localhost bot API's `level` stays readable, and `PATCH {level}` stays for it.

**Strategies: Off · Eyes · On** are `setup_levels` 0 / 1 / 2 under new names on the desk.
- Two template parameters join the bot group, which never restarts a read-out:
  - `bot_grades`: `"AB"` (default) or `"A"`. C stays NOT A TRADE.
  - `bot_setups_a_day`: 1 (default) or 2.
- `bot/first_pullback/admit.blockers` reads both from each setup's template in play:
  - a grade the template does not buy is `BOT_SKIP_GRADE` ("grade B: this strategy buys grade A only");
  - a setup whose `nth` is over `bot_setups_a_day` keeps its code `BOT_NOT_FIRST_OF_DAY` ("a 2nd first
    pullback: this strategy buys the 1st of the day only").
- The built-in template takes them too: `PATCH /api/setups/templates/{setup}/default` accepts bot-group
  values only (a name, a note or any scanner value is still `TEMPLATE_BUILTIN`). They are stored as
  `setups.{SETUP}.default_bot` in `setup-templates.json`, only the values that differ from the defaults,
  and the answer is `rules_changed: false` with the revision unchanged.
- A strategy at Off draws nothing on the charts.

**Today's hot list** (owner `backend/hot_list/`): the stocks Nova watches all day. Watching only (amended
2026-10-06, operator: "a starred ticker ... shouldn't be buying and selling if it's signal only"): a star never
decides who trades a stock, and taking one off never changes it -- that is the stock's Buy / Sell alone.
- **The file** is `hot-list.json` in the operator cache: `{schema_version: 1, date: "YYYY-MM-DD", auto_n: 0 | 3
  | 5 | 10, entries: [{symbol, how: "auto" | "star", at, board: "gainers" | null, rank: integer | null,
  change_pct: number | null}], yesterday: string[], reset_error?: string}`. A file written before
  2026-10-06 may carry `default: {buy, sell}` (the side a new name started on); it is read and dropped.
  `reset_error` is present only while today's 04:00 reset of the bot's buys failed (below).
  - `date` is the trading day, which starts at 04:00 ET; `at` is epoch seconds; `change_pct` is a fraction
    (0.6 = +60%), as on leaderboard rows. `yesterday` is the last day that had names, so Monday's
    bring-back finds Friday's.
  - Written through a temp file and a rename. An unknown version or an unreadable file reads as an
    empty list with the error stated, and writes are refused 409 `HOT_LIST_UNREADABLE` (also when the
    file cannot be written).
  - `HOT_LIST_CAP` is 20 and counts **stars only** (ADR 044 amendment, 2026-10-12): the auto feed can never
    refuse the operator's star. Auto stars have their own daily cap, `HOT_LIST_AUTO_CAP` (20). Each day is
    also kept read-only as `hot-list/YYYY-MM-DD.json` for the triggers audit.
- **Auto** (`hot_list/auto.py`), every `HOT_LIST_AUTO_TICK_SEC` from `HOT_LIST_AUTO_START_ET` (07:00) to
  `HOT_LIST_AUTO_END_ET` (16:00): the live Gainers board through `scanner_surface.surface_rows` and
  `leaderboard.ranking.rank_rows` with `LEADERS_RULES`, its top `auto_n`, never past `HOT_LIST_AUTO_CAP`
  auto stars. A name is added once a day and stays: one the operator takes off is not added again that
  day (remembered in memory, and re-read from the audit stream after a restart).
- **At 04:00 ET** (the day's reset of the bot's buys, run by the rollover):
  - `entries` move to `yesterday`;
  - every venue's bot list (`symbol_allowlist`) and every Auto-entry / Approve switch are cleared,
    with a `hot_list` audit line `{event: "rollover", cleared}`, so yesterday's choices never buy today;
  - trades Nova holds keep their exits.
  - The bot and Auto-entry buy nothing until today's file is written: `BOT_SKIP_DAY_NOT_RESET`
    (`hot_list.day_reset_block`; the auto feed's loop rolls over within `HOT_LIST_AUTO_TICK_SEC` of 04:00
    and at every start). When clearing the bot lists fails, today's file carries `reset_error`, the bot
    still buys nothing, and every later pass retries the lists (not the switches: one set since is today's);
    the retry that works writes a `rollover` line with `inputs.retry: true`.
- **Followed by the scanners.** The stocks the bot buys (Buy set to Bot on the desk's venue: its bot list,
  then each Auto-entry switch; `hot_list.following.bot_buy_symbols`), then listed names -- stars first, then
  auto stars, each in list order (`hot_list.listed_symbols`, 2026-10-12) -- share HOD Momo's 20
  reserved slots (`HOD_MOMO_FORMER_MOMO_MAX_SLOTS`) with Former Momo (`hod_momo_active.build_active_set`,
  `bot_symbols` then `hot_symbols`), then Former Momo fills what is left, so live movers keep at least 20 of
  the 40. A name on two lists counts once, as the first's. Past the 20 a name's admission reason is
  `bot_buy_over_reserved` / `hot_list_over_reserved` (it can still win a mover's slot on its own move); one
  IBKR cannot stream is `bot_buy_l1_blocked` / `hot_list_l1_blocked` and frees its slot. `GET
  /api/setups/symbol/{symbol}`'s `followed_note` says why a bot-buy or listed name is not followed.
- **Who trades the stock.** The stock's Buy / Sell switch (ADR 037) is the only "who", and the list is no
  part of it: starring, an auto star, bring-back and taking a stock off never change Buy / Sell, setting Buy
  to Bot never stars a stock, and the bot buys a stock whose Buy is Bot whether it is listed or not.
- **The mark.** On the desk a listed ticker carries a filled ★ (your star) or an outlined ☆ (an auto star)
  beside its symbol: scanner and Desk board rows, the Trader tab, the Focus rail, the HOD Momo strip, the
  quote card and the Who trades row (`watch_list/WatchMark.tsx`, `watchHow`).
- **Audited.** Every change is a `hot_list` line on the bot's audit stream, outcome and `inputs.event` one
  of `rollover` | `auto` | `star` | `remove` | `settings`, with the symbol where there is one (lines before
  2026-10-06 may also read `default`).
- **Routes** (writes need the API key):
  - `GET /api/hot-list` -> `{schema_version: 1, date, cap, auto_cap, auto: {n, start, end, rule, error},
    entries: [{symbol, how, at, board, rank, change_pct, followed: boolean | null, why_not_followed:
    string | null}], yesterday, error}` -- `why_not_followed` is null while `followed` is true: "HOD Momo's
    20 reserved slots are full", IBKR could not open the name's line, the scanner has not picked it up
    yet, or the active set has not been rebuilt since it was listed; `followed` is null when the scanner
    could not be read; `cap` is the stars' cap and `auto_cap` the auto stars' (2026-10-12);
  - `POST /api/hot-list/star {symbol}` -- on an auto star it makes it a star (counted against `cap`; the
    audit's star line carries `was: "auto"`); `409 HOT_LIST_FULL` once 20 stars are listed;
  - `DELETE /api/hot-list/{symbol}` (who trades it is unchanged; `HOT_LIST_NOVA_TRADE` is retired);
  - `PATCH /api/hot-list {auto_n?}`;
  - `POST /api/hot-list/bring-back` (yesterday's names as stars, up to the stars' cap).

  Every write answers the view.

**The squares, by ticker.** `GET /api/bot/triggers?date=YYYY-MM-DD` (default today: the hot list's
trading day, which starts at 04:00 ET, never the calendar date; owner `bot/trigger_audit.py`, read-only)
answers:

```
{schema_version: 1, date, generated_at,
 gates: [{id, label}],
 tickers: [{symbol, listed: {how, at} | null,
            now: {cells, answer: "yes" | "no", reasons} | null,
            market: {price, change_pct, change_abs, source, why} | null,
            triggers: [{ts, setup_id, setup_type, kind, nth, grade, tape, outcome, r, cells, reasons}]}],
 impact: [{gate, blocked, target_first, stop_first, r}],
 judged_now: string[],
 sources: {journal, audit, hot_list: {ok, error}}}
```

- **The gates**, in Nova's order: `bot_on`, `strategy_on`, `grade`, `setups_a_day`, `bot_window`,
  `nova_buys` ("Bot buys"), `level2_line`, `tape_go`, `trades_today`. The `hot_list` gate is retired
  (2026-10-06): being listed decides nothing, so no square asks it.
- **`cells`** maps each gate to `{ok: true | false | null, why}`; `null` means the gate did not apply.
  A trigger reads the bot's state, tape, grade (its `armed` line), `nth`, liquidity and outcome as the
  journal recorded them. It reads the stock's mode and the strategy's level from the audit stream at its
  moment. `judged_now` names the gates judged with today's
  settings because nothing recorded them.
- **`grade`** also carries NOT A TRADE's own checks (grade C, the spread, too thin), so every block has
  its red square.
- **A setting at a trigger** is the nearest audit record before it; one that a restart, a venue change or
  the rollover hides reads `null`.
- **The tickers**: the day's hot list (`listed`), then today's bot-buy stocks not on it, then every other
  ticker that triggered (`listed: null`).
- **BLIND** is the Level 2 line's red, never the tape's.
- **`now`** (today only, the trading day: the rows stay from midnight to the 04:00 rollover) is each
  listed or bot-buy ticker this minute; its `nova_buys` square is red while today's reset has not run.
- **`market`** (today only, every ticker; operator ask 2026-10-12: "a column that shows % change just like
  how the gainers does it"; owner `bot/trigger_market.py`) is where the ticker stands on the day, read as the
  quote panel reads it: its scanner row when a board holds it (gappers, gainers, losers, after hours, large
  cap, in that order), priced by its Level 1 line's last trade, else that line alone -- lines already held,
  nothing subscribes. `change_pct` is a fraction as the boards send it (0.25 = +25%), `change_abs` dollars
  against the prior close, `source` the board's name or `quote`. No change is `change_pct: null` with `why`:
  no trade yet (IBKR's prior close is not one, #541), no board and no line, a read that failed, or a Sim
  replay desk (its quotes are the replay's, the boards live). `null` on a past day.

**A hidden Trader tab lends its Level 2 and Time & Sales lines** (owner `backend/line_lending/`). IBKR
caps tick-by-tick lines too (ADR 044 took it for the depth lines' 3; on 2026-10-02 it carried 4 at once and
refused a 6th while Nova held 5, #698), so a loan moves both: a borrower
with a book and no prints would read WAIT, never GO.
- **When.** A setup of a strategy at On, on a stock whose Buy is Nova (Bot or Auto-entry), with the Bot on,
  is armed, near or in a trade; no line is free; and `line_lending` is on (`bot-session.json`, desk-wide,
  default true). Then the lines of a Trader tab that no visible window shows (the focus sensor) are lent to
  it. Checked every few seconds, so a setup has its lines before its trigger.
- **Never lent:** the tab in front, or one in front in the last 30 s; a line a Session Record, auto-record
  or the L2 recorder holds; a line a Level 2 outside a Trader tab watches; a stock Nova needs a line on
  itself; anything while the focus sensor cannot say which tab is in front.
- **On the lender's sockets.** A Trader tab opens `/ws/ibkr/depth/{symbol}` and `/ws/ibkr/tape/{symbol}` with
  `?tab=1&front=0|1`. Both send `{"type": "lent", symbol, to: {symbol, setup_type, setup_id}, why, tier,
  since, text}` (`why` in words, `tier` its code) and close. A socket opened with `front=1` -- the tab came
  to the front -- recalls the loan: both lines come back together, and the borrower's loss is said in the
  audit stream.
- **When it ends.** `setup_ended` (the setup failed or disarmed), `trade_ended` (the scoring window and
  Nova's trade are both over), `recalled`, `lending_off`.
- **Routes.**
  - `GET /api/ibkr/depth/lines` -> `{schema_version: 1, generated_at, cap, lines: [{symbol, held_by: "tab" |
    "record" | "auto_record" | "loan" | "replay", front: boolean | null, viewers}], lending: {on, error,
    loans: [{lender, borrower, setup_type, setup_id, since, why, tier, state, text, tape_lent, tape: boolean
    (a print arrived on the borrower's line), tape_state: "receiving" | "waiting" | "refused",
    tape_last_print, tape_error}], recent: [{lender, borrower, setup_type, setup_id, since, ended, end,
    tape_lent, text}]}}`. A borrower's tape line IBKR refuses or ends (10190) is `tape_state: "refused"`
    with `tape_error`, and is asked for again.
  - `PATCH /api/ibkr/depth/lending {on}` (API key) answers the same view; a `line_lending` audit line.
  - Every loan is a `line_loan` audit line: `lent` (with `tape_lent`, and the tape's error when the
    borrower got none), `ended`, `tape_refused` (once per refusal) and `tape_opened`.
- **On the desk** the lender's Level 2 and Time & Sales read "Level 2 lent to AISP's first pullback (near
  its trigger) -- back when it ends or when you bring this tab to the front". They reconnect when the loan
  ends or the tab comes to the front, never by their own backoff. A tab brought to the front within IBKR's
  15 s same-instrument rule shows its Time & Sales resubscribing for those seconds; the 10-second chart,
  built from those prints, has a gap for the length of the loan.

**On the desk.** The Bots page reads, top to bottom:
1. one answer line ("Can Nova buy right now?" for every ticker at once, each red with its fix, the
   desk's checks as chips);
2. the Bot card (the switch, Freeze all orders, the venue's risk);
3. the strategies, each Off · Eyes · On with its bot rules;
4. Level 2 lines;
5. Tickers today (the hot list and the squares);
6. Today, Proposals and Activity.

Elsewhere:
- **Freeze all orders** is the kill switch's name on the desk (`/api/kill-switch` unchanged). The
  header's red KILL is the one that flattens.
- **The Trader's chart toolbar has one Eyes switch** for every pane of the tab. `nova.stockRead.layers`
  `value` adds `eyes: boolean` (true when a stored value lacks it); off hides every Nova drawing, while
  `setups` / `levels` keep their own values for when it is on. A pane in full screen covers that toolbar and shows its
  own, and the Eyes switch is in it too (operator report 2026-10-13: "i also do not see the 'eyes' button";
  `components/chartToolbarExtra.ts`).
- **The Who trades row adds the ★** (on today's hot list; ☆ outlined for an auto star) and the stock's own
  answer ("Bot may buy AISP: no -- the bot is off").
- **Bot buy, bot sell** (operator, 2026-10-06: "Let's not have Nova buy and sell terminology"): every switch
  reads You | Bot, and the chart's calls BOT BUYS AT / BOT BOUGHT / BOT IS SELLING / BOT HOLDS THE EXIT. The
  wire keeps `"you" | "nova"`. Since short selling (ADR 048) the switches are Entry and Exit and the modes
  "you enter · you exit", "you approve · bot exits", "bot enters · you exit", "bot enters · bot exits".

## The bot trades a Sim replay (ADR 052, operator ask 2026-10-09, #814)

On the Sim desk off its live edge with a replay loaded (`sim.practice.loaded`: a Session Record or a
historical window), Nova's own bot trades like on Paper, on the Sim scratch account. Owner of the bot's
side: `backend/bot/replay_desk.py`; of the lanes: `backend/eyes/sim_eyes.py`, `eyes/sim_target.py`,
`eyes/history_recording.py`.

- **Activate** (`POST /api/bot/session/arm`) refuses `409 BOT_REPLAY_DESK` on Sim off the live edge only
  with nothing loaded ("load a Session Record or a download for the bot to trade ..."). The localhost bot
  API (`POST /api/bot/action`) still refuses every replay desk `409 BOT_LIVE_NOT_BUILT`, loaded or not:
  on a replay only Nova's own bot trades.
- **Triggers.** The Sim eyes' trigger event is the live one (`{symbol, setup_id, setup, tape, ts,
  template_id, template_rev, template_name, setup_type, grade, pillars, filtered, spread, liquidity, side,
  ssr}`) with `source: "sim"` and `replay_key` -- the scratch account's key, `["capture", SYMBOL, DATE]` or
  `["historical", SYMBOL, DATE, START, END]`. It is handed over only when the playhead played across it
  (no older than `BOT_FP_TRIGGER_MAX_AGE_SEC` at the playhead, on a forward step); a rebuild or a jump
  hands over nothing. The bot takes a trigger only from the feed the desk shows: `source != "sim"` on
  Paper and at the live edge, `source == "sim"` with the loaded `replay_key` on a replay.
- **The clock** of the bot's trade on Sim is the playhead: `entry_sent_ts`, `entry_cancel_ts`,
  `entry_filled_ts`, `exit_sent_ts`, `closed_ts` and the trigger's age are replay time, and stand still
  while it is paused.
- **The entry carries its own TTL** (#816): on a replay the bracket goes out with `good_for_sec` = the
  sleeve's `working_ttl_sec` ("A practice order's own expiry", `execution.md`), so the scratch account
  expires it at `entry_sent_ts` + TTL by itself. A jump of the playhead past that second never fills it on
  the prints the jump crossed: it ends `Expired` (`PRACTICE_GOOD_FOR_EXPIRED`) and the trade `missed`,
  "not filled in 3s", whether the expiry or the bot's own TTL cancel reached it first; a scrub back before
  that second restores it working. Paper and the live edge keep the bot's TTL cancel alone.
- **The trade** (`GET /api/bot/session` `trade`, `bot-session.json`) adds `replay_key: list | null` -- the
  replay it was made on; null on Paper and at the live edge -- and the state `rewound`: a trade on a
  replay this process did not make (a restart; the scratch account does not survive one), with `note`
  saying so. A trade with a `replay_key` is managed only while the desk shows that replay; its `waiting`
  text says what it waits on.
- **Rewind.** When the playhead goes back, the replay's part of the bot's `trade`, `working`, `bot_qty` and
  the replay's day count return to what they were at the new playhead (in-memory checkpoints by playhead);
  a live trade made elsewhere in the one `trade` slot (Paper, the live edge, another replay) is never
  touched. Loading another replay retires the old replay's live trade `rewound`, its working orders and
  shares with it; a `bot_trade`
  `note` line says so (`inputs.restored_to`), and an order of the bot's the restored trade does not know
  is cancelled (a `note` line names it). Each rewind changes the bot's idempotency keys on the replay
  (`bot:fp:sim:<replay>.<run>:<setup_id>:<step>`), so a setup played across again is sent again.
- **The day's count** on a replay (`entry_rules.today`, the `daily_cap` gate, `assert_entry_allowed`) is
  the replay run's own: the bot's entries sent before the playhead, a miss given back. Every bot audit
  line written on a replay carries `replay: {key, playhead_ts}`; such a line never counts toward any
  venue's daily cap in the audit fold.
- **What the bot reads** on a replay: last, bid and ask are the replay's at the playhead
  (`sim.practice.reference`, `bot.quotes`); the depth-line rule is met by the replay's own book --
  recorded Level 2, the window's NBBO, or a book Nova recorded that day -- beside the historical Level
  2's slot; the flush exit reads the Sim eyes' flow readings.
- **Who trades** (`GET /api/stock-mode/{symbol}`): `locks` adds `modes: {bot, auto_entry, approve}` --
  each mode's lock (null: open). On a replay `buy` / `sell` read null. With a replay loaded every mode is
  open (#815, below); with nothing loaded off the edge `modes` locks Auto-entry and Approve with
  `STOCK_MODE_WHY_REPLAY`, and `PUT` refuses them -- and "Nova takes the exit" -- `409 STOCK_MODE_REPLAY`,
  while Bot is taken.
- **Auto-entry, Approve and "Nova takes the exit" on a replay** (ADR 052 amendment, #815; owner of the
  replay side `backend/stock_mode/replay.py`). The stock-mode runner hears the Sim eyes' triggers as the bot
  does (only the feed the desk shows) and runs on the venue clock: `sent_at`, `filled_at`, `closed_at`,
  `cancel_sent_at`, an approval's `approved_at`, the exit's `trail_checked_at` and `raised[].at`, and the
  stock's `last_event.ts` are replay time on a replay; an Auto-entry or approved bracket entry on a replay
  carries `good_for_sec` = its `ttl_sec` (the bot's own expiry, #816), never its exits. A trade or approval
  made on a replay adds
  `replay_key: list` (null or absent elsewhere); it lives in memory only, never in `stock-mode-trades.json`,
  and is acted on only while the desk shows that replay -- one made at the live edge waits while the desk
  replays. A rewind returns the replay's trades, approvals and entries to what they were at the new playhead
  (checkpoints by playhead, also taken after each of the operator's acts; an approved bracket's first half too,
  #845: back before target 1's fill the trade's `halves` are empty and the scratch account's stop covers every
  share again), cancels an order of a replay
  trade the restored trades do not know, and changes the run tag in the stock-mode idempotency keys
  (`stock:<kind>:sim:<replay>.<run>:<SYMBOL>:<attempt>:<step>`); each is a `stock_mode` `note` line and the
  stock's last event. Another replay drops the old replay's trades and approvals, said the same way. The
  switch does not go back with a rewind. Auto-entry's entries on a replay share the bot's day count (sent
  before the playhead, a miss given back); Approve's count as `approved`.
- **The board** (`/ws/setups` on a replay desk): `replay.kind` is `capture` or `history` for a loaded
  replay (lanes over it) and `journal` with nothing loaded; `history` adds `source` (`massive` / `ibkr`)
  and `book` (`nbbo` / `none`), and `note` says what the tape gate reads. `recording` adds `book`
  (`l2` | `nbbo` | `none`). While a rewind waits for its rebuild, `rows`, `proposals` and `setups` are
  empty and `loading` is true -- never the lanes as they stood later.
- **The symbol's lanes** (`GET /api/setups/symbol/{symbol}`, the stock read's `setups`) on a replay are
  the Sim eyes' for the loaded symbol at the playhead, with `replay: true`; while they read the replay or
  catch up to a rewind, `followed` is false, `seeding` true and `followed_note` says which.
- **The stock read** (`GET /api/stock-read/{symbol}`) adds `replay: boolean`. On a replay desk it is the
  replay's at the playhead: `generated_at` and `session_date` are the playhead's, the setups and plan
  the Sim eyes', the levels from the Sim chart's completed candles up to the playhead, the daily map from
  the days before the replayed one; the live feed's facts are unknown. `nova_exit` is Nova's exit made on
  this replay. `past-setups` answers the Sim eyes' setups that ended (#815, `stock-read.md` "Setups that
  ended"); `decisions` answers empty with `replay: true` and a `note`; `history` adds `replay` and reads
  only the days before; `flush` reads `blind`.

## The Live Trader bot (ADR 055, operator ask 2026-10-14)

One bot per TraderTV host (`followed-traders.md`): it copies the host's bar on **Paper only**, never Live and
never Sim. Owner `backend/bot/live_trader/` (constants in `bot/live_trader/constants_live_trader.py`); the
Bots page's "Live Traders · TraderTV" section, under Strategies (`frontend/src/bot/`). On only while
`NOVA_FOLLOW_FEED_URL` is set: unset, the watcher asks nothing and the view says the feed is off.

**The rules** (ADR 055 decisions 2-4): a position on the host's bar is one step in their direction; an
add (their average moves; changes `LT_ADD_MERGE_SEC` 4 s apart are one add, acted on once settled, and one
back where it started is none) is one more step up to `adds`; the position leaving the bar sells or covers
the bot's whole position; off air (`traders[].seen.left_ts`, 60 s), the bar hidden `LT_HIDDEN_SEC` (600 s;
also a feed that has not answered or read for as long), and the sell-all time (`sell_all_at`, 15:55 ET; 12:55
on an early close) sell everything; an entry first seen `LT_OPEN_FRESH_SEC` (60) after it happened, on the
first answer of a watch, or when the host comes back on air is already open (`take_open`), taken only while the
host's bar shows it (`status.positions`; a trade the feed still holds open from before they left can be gone from
it: `LT_NOT_ON_BAR` after the wait). Opens and adds
skip, each with its reason: the feed `LT_FEED_BEHIND_SEC` (30) behind the stream or silent as long, a ticker
check not settled, the host's average over `LT_MISREAD_PCT` (1.5%) from the market (the mid, else the last),
a stock's market cap under `LARGE_CAP_MIN` ($10B) or unknown (an ETF always passes: Yahoo's `quote_type`
`"ETF"`, operator 2026-10-14), no fresh quote, the allowance, the adds, shorts off,
the account holding the other side (or the bot holding the other side for another host), outside the short
hours, the desk off Paper, the Bot switch off, Freeze all orders, after the sell-all time. A wait (the quote
line, the market cap, the ticker check) turns into its skip after `LT_WAIT_SEC` (30). Closes are never held
for a doubt -- a late read is still a true one; with no answer at all they wait for one, and `LT_HIDDEN_SEC`
without a read sells everything.

**Bad reads** (operator, 2026-10-14 ~23:15 ET: a read that looks "extremely abnormal" is flagged and waits for the
next one -- "I don't want it to try to buy more or try to average more"). A doubtful read never opens or adds; a
held position keeps its exits (the host's close as the feed confirmed it, off air, `LT_HIDDEN_SEC` without a
read, the sell-all time). Beyond the rules above, each with its reason:

- **Another host's row** (`LT_OTHER_HOST`): a row whose side, stock and average to the cent -- its entry's, its
  latest or one after an add -- are those of a row of another host on the bar within `LT_OTHER_HOST_SEC` (600) of
  it, or of any trade on the feed's previous day, is never opened, by either host's bot. At a hand-over the bar can
  show one host's rows under the next host's name tag for minutes, and two hosts never share an average to the cent.
- **A row the reader cannot read** (`LT_ROW_UNREAD`): while the host's reads in the read log (`followed-traders.md`,
  `reads.jsonl`) carried unparsed text for a side in the last `LT_UNREAD_SEC` (20) -- a row that scrolls (three or
  more positions on a side), cut or garbled -- nothing opens or adds on that side; the wait turns into its skip
  after `LT_WAIT_SEC`. Unparsed text that names no side (`long:` / `short:`) counts for both. No read log: no rule.
- **An implausible add** (`LT_ADD_IMPLAUSIBLE`): an add's new average lies between the host's average before it and
  the market (the mid, else the last), give or take `LT_ADD_SLACK_PCT` (0.5%) of the market; outside, it is a
  misread, skipped.
- **No clock** (`LT_NO_CLOCK`): a read without the stream's on-screen clock -- none, or one read impossibly
  (`09:34:97`, which the feed's parser drops) -- cannot say how far behind the stream it is: nothing opens until a
  clock reads. It is not a silent feed: it never counts toward `LT_HIDDEN_SEC`.
- A read the bot cannot make sense of at all (an answer it cannot fold) is a feed that is not answering
  (`LT_FEED_DOWN`, `state: "bad_answer"`): closes wait for a read, and `LT_HIDDEN_SEC` of it sells everything.

**Settings** (`live-trader-bots.json` in the operator cache; owner `bot/live_trader/settings.py`; written
through a temp file and a rename; an unknown version or an unreadable file refuses loud: every host reads
off and writes answer 409 `LIVE_TRADER_SETTINGS_UNREADABLE`):

```
{schema_version: 1, sell_all_at: "HH:MM" (ET, 09:30-15:55),
 hosts: {NAME: {key: bool, entry: "you" | "nova", exit: "you" | "nova", step_usd: 50-10000,
                adds: 0 | 2 | 4 | null (every add), allowance_usd: 100-50000, sides: "long" | "both",
                short_stop_pct: 1-20, take_open: bool, updated_at: epoch}}}
```

A host missing from the file reads key off with the defaults: `entry`/`exit` `"nova"`, `step_usd` 500,
`adds` 2, `allowance_usd` 2,500, `sides` `"both"`, `short_stop_pct` 5, `take_open` true. `NAME` is 1-16 of
`A-Z0-9`. `entry`/`exit` are stock mode's wire values (ADR 037): the mode is `stock_mode.model.mode_of`.

**What the bot holds** (`live-trader-book.json` in the operator cache; owner `bot/live_trader/book.py`;
temp file and rename; unknown version refuses loud, and the bot then opens nothing until it is fixed):

```
{schema_version: 1, day: "YYYY-MM-DD" (the desk's day, 04:00 ET),
 positions: [{id, host, row_id, symbol, side: "long" | "short", venue: "paper", qty, cost_usd, steps,
              adds_seen, adds_followed, opened_ts, state: "entering" | "open" | "closing",
              order: {id, step: "entry" | "add" | "already_open" | "close", sent_ts, qty, limit, stop} | null,
              stop_order_ids: [int], fills: [{step, qty, price, ts, order_id}], feed: {ts, price}}],
 closed: [{...the position, closed_ts, why, exit_fills: [{qty, price, ts, order_id}], pl_usd}],
 retire: [{order_id, symbol, host, since_ts}]}
```

`retire` (absent in an older file: empty) holds the buy stops of every position that holds no shares any more --
closed by the bot, covered outside it, stopped out, covered by the day cover, or an entry that never filled --
until Paper shows each one is not working: each pass cancels the ones still working, a refused cancel stays and is
tried again (a `live_trader` `error` line says so once), and a restart keeps the list. It is never cleared by the
day: a stop is off the list only when Paper says it is gone.

`id` is `host|side|symbol`: one position per host, side and stock (a feed row reopened for the same stock
is the same position, re-keyed to the new `row_id`, never bought twice). `closed` keeps today's (at most
200); a day other than today's is sold at once on load ("held from DAY: never overnight") and cleared.
Each pass reconciles with Paper's ledger: shares the account no longer holds (the operator sold them, a
buy stop or a breaker did) leave the position, said once. A short's buy stops cover what it held: when shares
of a short leave it that way, what the bot still holds of it is covered (change `kind: "outside"`), and once the
position holds nothing its stops wait on `retire` until Paper shows them cancelled -- a bot short never holds
without a stop for exactly its shares, and a stale stop can never buy past flat or cover a later short. A book that cannot be written stops every new step
(`can_trade.why` says so; closes go on) until a write succeeds; each pass tries again.

**Routes** (owner `bot/live_trader/routes.py`, under the bot router: loopback; writes need the API key):

- `GET /api/bot/live-traders` answers

  ```
  {schema_version: 1, generated_at, enabled: bool, venue: "paper", desk_venue,
   can_trade: {ok, why}, sell_all_at, sell_all_ts,
   watcher: {running, pass_ts, feed: {state: "ok" | "unreachable" | "bad_answer" | "off", error,
             read_age_sec, behind_sec, bar_visible, live}, text},
   hosts: [{name, face, on_air: bool | null, left_ts, settings: {...as stored, mode},
            state: {tone: "ok" | "warn" | "bad" | "off", text}, allowance: {used_usd, of_usd},
            today: {pl_usd, realized_usd, unrealized_usd, trades, skipped, series: [[ts, pl_usd]]},
            positions: [{id, row_id, symbol, side, qty, avg_cost, their_avg, now, pl_usd, steps,
                         adds_followed, opened_ts, state, order_id, note}],
            asks: [{id, row_id, symbol, side, step, their_price, qty, limit, stop, created_ts, expires_ts, text}],
            events: [{ts, tone, text, why}]}],
   defaults, bounds}
  ```

  `hosts` lists every host the feed read today -- read every `LT_IDLE_SEC` (15) while no key is on, so each
  host's card and its key show before any key is on (a desk with no settings would otherwise list none and offer
  no key to turn on) -- and every host with settings or positions, in the feed's
  order. `face` is the TraderTV LIVE page's photo path, or null. `events` are the host's newest
  `live_trader` audit lines (8), read from the audit file's last MB (`LT_AUDIT_TAIL_BYTES`) and again only when
  the file changed. `today.pl_usd` is realized plus unrealized at the last, from the bot's own
  fills; `series` its points at each fill.
- `GET /api/bot/live-traders/asks` answers `{schema_version: 1, generated_at, asks: [{...an ask, host,
  seconds_left}], held: [{host, symbol, side, qty, state}]}` from memory only: every desk window polls it for
  the asks' toasts, and the Bot switch reads `held` before it asks to sell.
- `PATCH /api/bot/live-traders {sell_all_at}` and `PATCH /api/bot/live-traders/{name} {key?, entry?, exit?,
  step_usd?, adds?, allowance_usd?, sides?, short_stop_pct?, take_open?}` answer the view; a value out of
  bounds is 400 `LIVE_TRADER_INVALID` with `field`, never clamped. `key: false` while the host's bot holds
  positions sells them on the next pass (the desk asks first). Each change is a `live_trader` `settings`
  audit line `{host, from, to}`.
- `POST /api/bot/live-traders/{name}/asks/{ask_id} {approve: bool}` answers the view; an ask that expired,
  was answered or was withdrawn (the host closed) is 409 `LIVE_TRADER_ASK_GONE`. An approved step meets
  every rule again on the next pass before it is sent.

**Orders** (ADR 055 decision 5): every one through `execution.service.execute`, `origin: "live_trader"`,
`setup: "live_trader:<NAME>"`, an idempotency key unique to each send (`bot:lt:paper:<row id>:<step><n>:<ms>`:
the same trade can be taken again after the host comes back on air, and a reused key would replay the earlier
send's receipt). A long entry or add
is a `place` BUY `LMT` at the ask plus `LT_ENTRY_OFFSET_USD` (2 cents; the last when no ask), source `bot`,
`expected_venue: "paper"`; a short one a `bracket` SELL `LMT` at the bid less 2 cents (over the bid while
SSR is on or unknown, as the setup bot prices it) with `short_entry` and a BUY stop `short_stop_pct` over
it, no target. Working after the Paper sleeve's `working_ttl_sec`, it is cancelled. A close cancels the
position's buy stops (source `cancel_working`) and sends the protective flatten (source `flatten`, the
practice market ticket) for the bot's shares, never more than the account holds; both name
`target_venue: "paper"`. `live_trader` is one of the door's Nova-close origins on Paper and Sim only
(`execution.md`, "Who sent it").

**Lines.** `ibkr.ticks.set_owner_symbols("live_trader", ...)` holds a Level 1 line on every stock the bot
holds, is entering or waits to enter; never a Level 2 line (ADR 055 decision 3).

**Audit** (the bot's stream): action `live_trader`, outcome `order` (a step sent) | `filled` | `closed` (a
close sent) | `skipped` | `asked` | `answered` | `refused` (the door's words) | `settings` | `note` |
`error`; `inputs: {host, row_id, symbol, side, step, qty, limit, stop, order_id, code, why, change: {kind:
"open" | "add" | "already_open" | "close" | "off_air" | "hidden" | "sell_all" | "key_off" | "bot_off" |
"stale_day" | "outside", ts, price}, late_sec, venue: "paper"}`. `late_sec` is the send's wall time less the feed's
time of the change. A skip is written once per position, step and code. Codes: `LT_FEED_BEHIND`,
`LT_FEED_DOWN`, `LT_TICKER_UNSETTLED`, `LT_MISREAD`, `LT_SMALL_CAP`, `LT_CAP_UNKNOWN`, `LT_NO_QUOTE`,
`LT_ALLOWANCE`, `LT_ADDS_DONE`, `LT_SHORTS_OFF`, `LT_AGAINST`, `LT_NOT_HELD`, `LT_VENUE`, `LT_BOT_OFF`,
`LT_FROZEN`, `LT_AFTER_SELL_ALL`, `LT_SHORT_HOURS`, `LT_NOT_PRICEABLE`, `LT_ASK_EXPIRED`, `LT_ASK_SKIPPED`,
`LT_ALREADY_OPEN`, `LT_OFF_AIR`, `LT_HIDDEN`, `LT_DAY_LOCK`, `LT_NOT_ON_BAR`, `LT_OTHER_HOST`, `LT_ROW_UNREAD`,
`LT_ADD_IMPLAUSIBLE`, `LT_NO_CLOCK`.

**The Bot switch** counts a host key on as a strategy On on Paper (`BOT_NO_SETUP_AT_STRATEGY`: "no
strategy is On and no Live Trader key is on"); `GET /api/bot/session`'s `setups` gate adds
`live_traders: [NAME]`. The operator's OFF (`POST /api/bot/session/switch {on: false}`) on Paper while the
Live Trader bot holds positions sells them on the next pass (the desk asks first); a `live_trader` `closed` line
names `bot_off`. Sim's and Live's switches never touch the Paper bot's shares.

**On the desk.** The section's cards (mockup v1, approved 2026-10-14): the host's photo or initial, on air
and how old the read is, the key, Entry You | Bot and Exit You | Bot with the mode in words, the allowance
bar, today's P/L, trades and skips with a line of the day's P/L, the positions (shares, the bot's cost, the
host's average, now, P/L), the last events with their reasons, and the settings as chips that open their
editors. A line above the cards says what stops every host now (`can_trade.why`). An ask is a line on its
card and a toast in every desk window (`bot/BotNotices.tsx`) with Skip and Approve and its seconds left.
Turning a key off, or the Bot switch off, while positions are held asks "Sell N and turn off".
