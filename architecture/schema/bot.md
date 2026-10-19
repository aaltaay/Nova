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
budget (and `/api/bot/advise*`, which nothing called), and moves the sleeve and the
bot list into each venue's dial (below). A watch-only setup (#847,
the pullback dip, and the ABCD; setups.md "The pullback dip: a watch-only setup", "The ABCD: a
watch-only setup") is never
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
stream (the day is Nova's trading day, `market.session_key_et`: the count resets at 04:00 ET,
never at midnight, 2026-10-19; entry audit rows carry `inputs.venue_day`; an entry cancelled unfilled
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
`BOT_COMMISSIONS_WARN_EVERY_SEC`), never read as $0. The commission loop (`bot.loops.commission_loop`,
every `BOT_COMMISSION_POLL_SEC`) keeps the hold current. **The day P&L meter reads
IBKR's own figure** (ADR 042 / #664; nothing compares it since ADR 056): on Live, the finite `dailyPnL` from
`reqPnL` for the current READY IB instance, generation and account. IBKR owns
that figure's reset (the TWS configuration, not Nova's 04:00 ET lock boundary);
the API supplies no reset timestamp, so the meter never invents one. Pending,
failed, disconnected or superseded subscriptions cannot supply cached daily
P&L. While it is unavailable, the stated fallback is `RealizedPnL + UnrealizedPnL`,
which can include an overnight position's lifetime move. Both broker figures
already include commissions (TWS Users' Guide, Profit and Loss) -- until
2026-09-30 the retired breakers subtracted the session's commissions again; on Paper and Sim at the live edge, the practice
ledger's `DayPnL`; on a replay desk nothing (a replay's P&L is not today's).
`GET /api/bot/pnl`'s meter says which: `{compares, source, venue, compared,
note, error, day_pnl, commissions, commissions_in_figure, commissions_unknown,
commissions_error, fallback, fallback_reason, reset_semantics, reset_time,
daily_pnl_updated_at, ...}`. The fallback and its limitation are visible; no
session commission is subtracted again. A commission read failure still holds
new Live bot entries without invalidating the known P&L. Practice day boundaries
and trading authorization are unchanged.
Proposals are accepted at Eyes and Strategy. **Every gate is drawn with its
reason** (owner `bot/gates.py`): `gates: [{id, ok, stage: "activate" | "fire",
detail: {..., text}}]` are `venue` (Paper, or Sim at its live edge), `level`
(the master at Strategy), `setups` (`at_strategy`), `padlock`, `allowlist`
(stocks set to Bot or to Auto-entry on this venue; stage `fire`, so it never
locks Activate -- Auto-entry needs the bot Active), `depth_lines` (ok while at
least one Bot stock holds a depth line, `held`, `missing`, `max_lines`; each
trigger still needs its own), `loss_limit` (stage `fire`: the daily loss limit's No new
buys on this venue, `detail: {text, until, tripped_at, loss, limit_usd, venue}`; `loss-limit.md`), `kill_switch`, `window`
(per Strategy setup: `setups: [{setup, start, end, open, clipped, error}]`),
`daily_cap` (`count`, `cap`, `venue_day`), `extended_hours` and `commissions`;
the session adds `ready` / `ready_reason` (the bot would trade a go trigger now)
with `live_fire_ready` as a one-release alias.

**Activate: one control, one meaning, never carried** (ADR 042, owner
`bot/activation.py`). `POST /api/bot/session/arm` refuses, `409`
with a plain reason: `BOT_LIVE_NOT_BUILT` (Live), `BOT_REPLAY_DESK` (Sim off the
live edge with nothing loaded; a loaded replay is traded, ADR 052), `BOT_VENUE_UNKNOWN`, `BOT_LEVEL_NOT_STRATEGY`,
`BOT_NO_SETUP_AT_STRATEGY` and `BOT_PADLOCK_LOCKED` (the legacy `/arm` alone still refuses a locked padlock; the Bot
switch does not, "The Bot switch" below). No loss limit refuses Activate or turns
the bot off (ADR 056). Choosing Strategy never activates. The backend clears
Activate -- a `deactivate` audit line and `deactivated: {at, reason, text}`,
`reason` one of `restart | venue | level | operator` (older lines also `padlock` and `no_setup`; a saved
`bot_trip` / `all_stop` from before ADR 056 keeps its own `text`) -- on every process start (like spend arming, ADR 018),
on a venue change, with the master below Strategy, and by the operator. Locking the padlock no longer clears it
(operator decision 2026-10-16, "The Bot switch" below): while it is locked every bot holds instead. A saved `padlock`
stamp from before that reads today's words (`activation.stamp_text`), never "it unlocks the padlock". The
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

**No loss breaker** (ADR 056, superseding ADR 032). The bot trip and the all-stop are gone, with
their thresholds (`breakers`), the bot trip's latch (`soft_breaker_*`), the all-stop's day lock
(`hard_lock_*`, `day_lock`, `day_locks`, `day_lock_active`), the `bot_trip` / `day_lock` gates,
`BOT_TRIP_LATCHED`, `reenable`, `switch.latched` and the breaker notices. `PATCH /api/bot/session
{breakers}` is refused `400 BOT_BREAKERS_RETIRED` with the words "The bot trip and the all-stop are
gone: set the daily loss limit in Settings > Loss limits (ADR 056)". A saved session with any of their
fields -- on the row or in a venue's dial -- loads with them dropped (`BOT_RETIRED_BREAKER_KEYS`). The
one loss limit is the operator's, in Settings, for you and the bots alike (`loss-limit.md`); it never
turns the bot off, and the bot meets its No new buys at the execution door and in its `loss_limit` gate.
`bot-session.json` and `bot-proposals.json` are written through a temp file and a rename.

**The level belongs to a venue** (operator report 2026-09-30: "When I switch
between L0 and L2 in the paper, it stays persistent when I switch to live, and
I feel like that shouldn't happen"; owner `bot/venue_levels.py`). Each venue
keeps its own dial -- `level`, `setup_levels`, the sleeve (`caps`), the bot list
(`symbol_allowlist`; Live's starts empty: Nova never buys on Live) and the bot's
`working` orders and `bot_qty` -- the session's fields being the dial of
the venue in `level_venue` and the others waiting in `venue_levels: {VENUE:
dial}` (optional keys of schema 4; a venue with none starts Off). `sim.mode.set_venue` puts the old venue's dial away, takes the new
one's and deactivates the bot (a `venue` audit line): Activate never carries
into another venue, like spend arming. A session loaded on another venue than
its `level_venue` takes that venue's dial; one without the stamp belongs to the
venue the desk showed. `GET /api/bot/session` adds `level_venue` and
`levels_by_venue: {live, paper, sim}`. Leaving a venue first cancels Nova's
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
line, the padlock, the kill switch, this venue's daily loss limit (ADR 056), the
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
`missed` | `partial` | `filled` | `half` | `closing` | `closed` | `handed` | `note` | `error`, `inputs` with
the `setup_id`; the names and the `partial` line: "Fills on the bot audit stream" below). A bot working order the bot cancels itself carries
`expire_ts: null` in `working`.

## One Bots page (ADR 044, operator decisions 2026-10-01)

"I definitely don't like it if we have redundancies ... put everything on one page", after AISP's three
triggers went unbought for five reasons no screen showed together. ADR 044 amends ADR 042, 037, 041,
036, 032 and 023 as below.

**The Bot switch.** One per venue, on the desk in place of the master dial and Activate; since 2026-10-15 it is
in the header beside the padlock, on every view (it was on the Bots page's Bot card). `POST
/api/bot/session/switch {on: boolean}` (API key) answers the session view.
- **ON** puts the venue's master `level` at Strategy (2) and activates. It is refused like Activate:
  409 `BOT_LIVE_NOT_BUILT`, `BOT_REPLAY_DESK`, `BOT_VENUE_UNKNOWN` and `BOT_NO_SETUP_AT_STRATEGY` (no
  strategy is On). A successful ON returns `desk_arm_token`,
  as `/arm` does.
- **The padlock is separate** (operator decision 2026-10-16, replacing the 2026-10-12 amendment "ON unlocks the
  padlock"): ON neither unlocks the padlock nor needs it, and locking the padlock -- by anyone -- leaves the switch
  on. While it is locked no one places an order, a bot included: every bot reads it before each send
  (`family_keys.hold`, code `BOT_PADLOCK_LOCKED`, a Live Trader skip `LT_BOT_OFF` with the padlock's words), and the
  bots trade again the moment it is unlocked. Header KILL still turns the bot off (it drops the master to Off).
  `deactivated.reason: "padlock"` is only on lines written before 2026-10-16.
- **OFF** deactivates (`deactivated.reason: "operator"`) and puts the master at Eyes (1), so setups
  at Eyes or On still propose. Turning it off sells nothing, and while it is off no bot of either family places
  any order, not even a sell ("The three keys" below).
- No loss limit turns the switch off (ADR 056): the daily loss limit's No new buys holds the bot's
  entries at the door and in its `loss_limit` gate.
- Each change is a `bot_switch` audit line, outcome `on` | `off`, `inputs: {on, from_level, to_level}`.
- The session view adds `bot_on: boolean` (active with the master at Strategy) and `switch: {on, venue,
  why_off: string | null}`.
- The localhost bot API's `level` stays readable, and `PATCH {level}` stays for it.

**The three keys** (operator decisions 2026-10-15: Bots as a group with "a key per family, and one super key by the
header lock"; off at every level: "Bots can not place order or sell orders! that's it", then, asked what a held
position does, "No orders at all"). A bot places an order only while all three of its keys are on, on its venue:

1. **The Bot switch** (the super key, above): every bot on the venue.
2. **Its family's key**: **Strategy Bots** (the setup strategies' bot and Auto-entry) at the top of Bots > Strategy
   Bots; **LiveTrader Bots** (ADR 055) in the head of Bots > LiveTrader Bots. Each covers only its own family.
3. **Its own key**: each strategy's Off · Eyes · On; each TraderTV host's Bot key.

- **Off places no order at all, at every level** -- no entry, no add, no sell, no cover, no stop moved. Nothing is
  sold when a key turns off, and what a bot holds stays until the keys are back on or the operator sells it: the Live
  Trader bot neither follows the host's exits nor sells at off air, the 10-minute hidden rule, the sell-all time or a
  day rollover; the strategy bot sends no time stop, flush exit or tightened stop and leaves a close under way as it
  rests. What already rests at the broker still fills (a bracket's stop and target, a short's buy stop), and the bot
  still reads those fills. Each held position says so once (a `note` line). When the keys are back on, an exit whose
  reason still stands is sent then (past the sell-all time: at once).
- **What a bot still does with a key off:** it takes back its own orders, which places nothing -- an entry not filled
  by its time to live is cancelled, and the stops of a position that holds nothing are cancelled. One exception, so
  that a bot's stop can never flip an account the wrong way: when the operator covers part of a Live Trader short by
  hand, its bot still covers the rest, whose buy stop no longer matches (ADR 055, "bad reads" review).
- The keys stop bots, never the operator: your own orders, a cover included, go through the door with every key off.
  Header KILL and Freeze all orders are unchanged; bots never trade Live.
- **On flows up** (operator ask 2026-10-16: "I don't want to be controlling 100 manual switches"; owner
  `bot/cascade.py`): a TraderTV host's Bot key turned on (`PATCH /api/bot/live-traders/{name} {key: true}`) turns the
  LiveTrader Bots key on, then the Bot switch; a strategy turned On through `PATCH /api/bot/session {setup_levels}`
  turns the Strategy Bots key on, then the Bot switch; a family key turned on (`POST /api/bot/session/keys`) turns
  the Bot switch on, and that answer carries `desk_arm_token` when it did. Each step is the same press with the same
  rules and audit line as by hand. A parent that cannot follow (Live, a replay desk, an unreadable keys file, nothing
  On under the switch) stays as it is and its own `why_off` says why; the press that asked still counts. Off never
  flows up, and the padlock is never part of it.
- **The Bot switch no longer follows the keys under it** (2026-10-15): turning the last strategy Off, or the last
  host key off, leaves it on -- with off at any level meaning no order, a lower key turning it off would also stop
  the other family's exits. ON is still refused while no strategy is On and no host key is on
  (`BOT_NO_SETUP_AT_STRATEGY`), and it still goes off at a start and a venue change (no longer at a locked padlock,
  2026-10-16).
- **The family keys' file** is `bot-keys.json` in the operator cache (owner `bot/family_keys.py`; a temp file and a
  rename): `{schema_version: 1, venues: {paper | sim: {strategy: boolean, live_trader: boolean, at: epoch}}}`. Paper and
  Sim each keep their own; Live has none (they read off: bots never trade Live). A venue or a family missing from the
  file reads **on**, so the update trades as the day before until the operator turns one off. An unknown version or
  an unreadable file reads every family key off with the reason and refuses writes 409 `BOT_KEYS_UNREADABLE`. A
  process start and a venue change keep the keys; only the Bot switch never survives a start (ADR 042 B).
- `POST /api/bot/session/keys {family: "strategy" | "live_trader", on: boolean}` (API key) answers the session view;
  on Live it is 409 `BOT_LIVE_NOT_BUILT`, on an unreadable venue 409 `BOT_VENUE_UNKNOWN`. Each change is a `bot_key`
  audit line, outcome `on` | `off`, `inputs: {family, venue, on}`; pressing a key into its own state writes nothing.
- The session view adds `keys: {venue, error: string | null, strategy: {on, why_off}, live_trader: {on, why_off}}`
  for the desk venue (`why_off` null while on).
- **Strategy Bots off**: the bot and Auto-entry skip a go trigger `BOT_SKIP_FAMILY_OFF`, the runner does not play, the
  bot's open trade is only read (above), the localhost bot API (`POST /api/bot/action`) refuses every order kind 409
  `BOT_SKIP_FAMILY_OFF` (`cancel_symbol` still goes), and the session's `gates` add `strategy_key` (stage `fire`).
- **A strategy below On** is its trade's own key off: the bot's open trade of that strategy is only read, said once
  (`BOT_SETUP_NOT_STRATEGY`), until it is On again. The squares' `bot_on` square is green only with the Bot
  switch and the Strategy Bots key both on; a past trigger reads the key from the journal's `bot` stamp
  (`strategy_key`; a line without it is judged by the Bot switch alone).
- **LiveTrader Bots off**: `LT_FAMILY_OFF` ("The Live Trader bot" below).

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

**The squares, by ticker.** `GET /api/bot/triggers?date=YYYY-MM-DD` (default today: Nova's
trading day, `market.session_key_et`, which starts at 04:00 ET and keeps the last exchange day over a weekend or holiday, never the calendar date; owner `bot/trigger_audit.py`, read-only)
answers (the eyes' journal is filed by calendar date, so its lines stamped before the day's 04:00 ET belong to
the day before and are left out of the day's table and of its restart marks, 2026-10-19):

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

**On the desk.** The nav rail's **Bots** is a group (operator decision 2026-10-15): **Bots** itself, empty for now
("keep it empty for now"), then its two children, **LiveTrader Bots** (the TraderTV hosts' page, each host's bot in their
card, "The Live Trader bot" below) and **Strategy Bots**, the page that was Bots, unchanged but for the key on top. Strategy Bots reads, top to
bottom:
1. the Strategy Bots key;
2. one answer line ("Can Nova buy right now?" for every ticker at once, each red with its fix, the
   desk's checks as chips);
3. the Bot card (Freeze all orders, the venue's risk; its switch is the header's);
4. the strategies, each Off · Eyes · On with its bot rules;
5. Level 2 lines;
6. Tickers today (the hot list and the squares);
7. Today, Proposals and Activity.

The header's Bot switch sits beside the padlock: Bot ON / OFF for the desk venue, a press turns it on or off, a
refused press says why under it, and hover says why it is off. Every link that opened the Bots page opens Strategy
Bots.

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
desk, **Bots > LiveTrader Bots**: the followed traders' page (`followed-traders.md`, "On the desk"), with each
host's bot in the middle of their card, between their record and their P/L (operator, 2026-10-15: "i want all content
from the original tradertv live to be inside livetrader bots", and the panel's "Entry you/bot exit you/bot .. can all be
compacted inside these empty spaces... includeing bot keys"; approved from a render, "i like it. build it."). The
"Live Traders · TraderTV" panel that stood on its own on that tab is gone. Under the hosts the page carries the
desk's Positions / Orders · today dock -- the Scanner's own (`ScannerDesk`, `data-dock-host="bots"`), resizable and
collapsible, its split kept apart (operator ask 2026-10-16: "I do want to see the positions tab"). On today, a host's bot reads in two lines:
its Bot key, Entry You | Bot, Exit You | Bot and Rules (the rules on hover; a click opens their editor in a card
under it); then the allowance used of its allowance, Today's P/L, trades and skips -- the skips' reasons on hover, by
reason, from its newest events. An ask waiting on the operator takes the second line, with Skip, Approve and its
seconds; a write refused takes it with why. A copy the bot holds is a BOT chip on the host's open row it copies
(`row_id`), its shares, entry and P/L on hover; one whose row is gone (a key held its close) is a chip on the second
line. A card narrower than 1300 px puts the two lines on one line of their own under the card's row. The page's
head holds the LiveTrader Bots key and, while `can_trade` is not ok, one amber line, "No orders · "
and the reason's first clause (all of it on hover); `LT_FROZEN` links to Strategy Bots, where Freeze all orders
is, and `LT_LOSS_LIMIT` says Settings > Loss limits in its words (ADR 056); a window under 2100 px gives the key
and that line a line of their own under the head's row. The keys it obeys are the header's Bot
switch, that key and the host's own ("The three keys"). Its styles are its own (`bot/liveTraderStrip.css`). On only while `NOVA_FOLLOW_FEED_URL` is set: unset,
the watcher asks nothing and the view says the feed is off.

**The rules** (ADR 055 decisions 2-4): a position on the host's bar is one step in their direction; an
add (their average moves; changes `LT_ADD_MERGE_SEC` 4 s apart are one add, acted on once settled, and one
back where it started, to the cent the bar shows (a hundredth of a cent under $1), is none -- an add of a few cents on a large cap is an add) is one more step up to `adds`; the position leaving the bar sells or covers
the bot's whole position; off air (`traders[].seen.left_ts`, 60 s), the bar hidden `LT_HIDDEN_SEC` (600 s;
also a feed that has not answered or read for as long), and the sell-all time (`sell_all_at`, 15:55 ET; 12:55
on an early close) sell everything; an entry first seen `LT_OPEN_FRESH_SEC` (60) after it happened, on the
first answer of a watch, when the host comes back on air, or that fills an empty bar together with others ("The
bar's own moves" below) is already open (`take_open`), taken only while the
host's bar shows it (`status.positions`; a trade the feed still holds open from before they left can be gone from
it: `LT_NOT_ON_BAR` after the wait). Opens and adds
skip, each with its reason: the feed `LT_FEED_BEHIND_SEC` (30) behind the stream or silent as long, a ticker
check not settled, the host's average over `LT_MISREAD_PCT` (1.5%) from the market (the mid, else the last) --
`LT_MISREAD`, or `LT_OPEN_TOO_FAR` for a position already open, the market gone on from the average the host held it
at (2026-10-16: SHAWN's TSLA short held through the lunch break came back 2.8% in profit and read "a misread"),
a stock's market cap under `LARGE_CAP_MIN` ($10B) or unknown (an ETF always passes: Yahoo's `quote_type`
`"ETF"`, operator 2026-10-14), no fresh quote, the allowance, the adds, shorts off,
the account holding the other side (or the bot holding the other side for another host) -- while every such
position of the bot is closing (its close sent that pass or in flight: a host's flip, long to short at once), the
entry waits for the bot to be flat and turns into its skip after `LT_WAIT_SEC` -- outside the short
hours, the desk off Paper, the Bot switch off, the LiveTrader Bots key off, Freeze all orders, after the sell-all
time. With the Bot switch, the LiveTrader Bots key or the host's own key off, the host's bot places no order at all
("The three keys"): each add of what it holds is a skip (`LT_KEY_OFF` for the host's key), so turning a key back on
never buys an add made while it was off, and each close it would have sent is said once ("not sold -- ...", with
the position's wait) and sent when the keys are back on if its reason still stands. A position held from an earlier
desk day is judged from its own open time on every pass, so one a key held back at the rollover is sold the pass the
keys are back on, whatever its Exit. A wait (the quote
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
- **A sale read as an add** (`LT_ADD_IS_SALE`; operator 2026-10-16, "the point is to emulate them as much as
  possible"): an average that fell while the market stayed over the old one by more than `LT_ADD_DIRECTION_PCT`
  (0.1%) of it the whole time since the change (rose while it stayed under, on a short) is a partial sale the host's
  platform folded into the average (each sale's profit lowers it), never a buy: skipped, nothing bought. "The whole
  time" is the market's low and high from `LT_SALE_LEAD_SEC` (5 s) before the change on (`market.range_since`: each
  held stock's market sampled each pass, `LT_PRICE_KEEP_SEC` (180 s), memory only); a market that crossed their old
  average since then could have made a real add, so it is judged as one (Codex review, PR #1022). Without samples
  reaching back that far (a restart), the market now stands for the window. It is judged before the
  `adds` limit, so it is seen after every add is spent. The first such sale of a long the bot holds sells half its
  shares (rounded down) at market, once per position (operator, "Sell half, once": the bar shows the average, never
  the shares sold): a `close` with `trim: true`, change kind `trim`, its fill an `exit_fills` row of kind `trim`, and
  the position then carries `trimmed: true` -- a later sale sells nothing more, the rest waits for the host's close.
  A short keeps every share (Paper cannot shrink its buy stop to the shares left), a single share has no half, and
  Exit: You keeps them; each is said as a `note`. A sale is judged as every add is (`read_doubt`, the band, `rules.check`) before it trims. One that comes while a step is blocked -- a key, the Bot switch, Freeze all orders -- waits on its row (memory) and the half sells the pass they are back on, said once ("not sold -- ...; the bot sells half when it is back on"); a restart forgets it. SHAWN's TSLA,
  2026-10-16: TSLA rose 365 -> 370 while his average fell 366.50 -> 365.02, and at 09:59 it fell 364.32 -> 364.02
  with TSLA at 366.8; the bot had bought that as an add.
- **No clock** (`LT_NO_CLOCK`): a read without the stream's on-screen clock -- none, or one read impossibly
  (`09:34:97`, which the feed's parser drops) -- cannot say how far behind the stream it is: nothing opens until a
  clock reads. It is not a silent feed: it never counts toward `LT_HIDDEN_SEC`.
- A read the bot cannot make sense of at all (an answer it cannot fold) is a feed that is not answering
  (`LT_FEED_DOWN`, `state: "bad_answer"`): closes wait for a read, and `LT_HIDDEN_SEC` of it sells everything.

**The bar's own moves** (operator, 2026-10-15: hold the sells while a whole bar blanks, up to 90 s; owner
`bot/live_trader/decide_bar.py`, state in the decision's snapshot, memory only). The bar can change on screen
without the host trading. The answer carries each host's `bar` as the feed last confirmed it (`status.positions`:
`["side:SYMBOL"]`, `[]` when it reads empty on both sides, null when the feed sends none).

- **A blank bar** (`LT_BLANK_BAR`): every open position of a host -- two or more -- closes in the feed within
  `LT_SWITCH_SEC` (1 s) of each other, no other row of theirs open, while their `bar` reads `[]` (or is already
  back). That is a display refresh: the same positions come back about a minute later at their very averages. The
  closes of those rows wait, said once per position (a `note`), up to `LT_BLANK_HOLD_SEC` (90 s, the stream's clock
  or the wall's, whichever is further). Once the bar's first row is back and `LT_BLANK_SETTLE_SEC` (4 s) has passed,
  a position back at its very average -- side, stock, and its last average to the cent equal to the new row's entry
  or average -- is the same position: re-keyed to the new row (`rekey`), nothing sold, nothing bought, its adds
  followed from the new row, and every row back inherits its old row's decision (a skip is not said twice). A
  position not back is sold then ("the bar came back after the blank without ..."). The bar still empty at the limit:
  everything is sold ("stayed empty 90 s"). A bar not read empty, closes further apart, a position left open beside
  them, or no `bar` from the feed: the closes sell at once, as before. While a host's bar is blank, no take of theirs
  is made. Off air, `LT_HIDDEN_SEC`, the sell-all time, the key and the Bot switch never wait: they sell at once. A
  real flatten-all that the host makes in one second reads the same way and is sold up to 90 s late.
- **A hand-over that lingers** (`LT_RETURN_SWITCH`): after a host comes back on air the bar can show the previous
  host's rows under their name tag until every slot switches at once. The rows the bar shows in the first
  `LT_RETURN_FIRST_SEC` (30 s) after the return -- until one of them closes -- are not taken (a `note` each) until
  every one of them has closed (the switch), or `LT_RETURN_HOLD_SEC` (480 s) passes; then they are already open
  (`take_open`), as any row is. Rows that open later, and rows of a host on air all along, are judged as before.
- **A stock the feed reads two ways** (#1010; operator OK 2026-10-15 for the rule "a row the feed closed and opened
  again in the same second for the same stock is the same position, re-keyed, never sold and bought again"). A
  misread that flips between two readings of one bar ("RGTI 12.08" read in turn as RGT 112.08, RGTI 112.08 and
  RGTI 12.08) makes the feed close the trade and open the next in one second. The feed cannot close and open one
  stock in one read, so before a closed row sells, the bot looks for an open row of the same host and side, not
  left the bar, whose `entry_ts` is in the closed row's `exit_ts` second and whose stock is the position's -- or
  whose ticker check is still `checking` with the position's stock as its glued reading (`ticker.other_symbol`):
  for a few seconds after the flip the row back reads under the glued ticker. Found, it is the same position:
  re-keyed (`rekey`, "the feed read X again in the same second"), nothing sold, nothing bought. While its check runs,
  the row back under the glued ticker opens nothing. Should the check settle on the other stock (the glued reading
  was a real ticker at that price), it was a hand-over after all: the position sells ("the row back at T is RGT, not
  RGTI") and the row is judged as any other. A close with no same-second row back, and a different stock opened in
  that second (a hand-over), still sell. Off
  air, `LT_HIDDEN_SEC`, the sell-all time and the keys judge first, as for every close.
- **Rows that fill an empty bar together are already open** (`feed_rows.filled_together`): two or more slots
  changing within `LT_SWITCH_SEC` onto an empty bar -- rows opening together while every older row of the host has
  closed by then (a bar back after a blank, the slots switching at a hand-over) -- were already open, not entered.

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
              adds_seen, adds_followed, trimmed (absent: false), opened_ts, state: "entering" | "open" | "closing",
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
is the same position, re-keyed to the new `row_id`, never bought twice; so is one closed and opened again in
the same second, "A stock the feed reads two ways"). `closed` keeps today's (at most
200); a day other than today's is sold at once on load ("held from DAY: never overnight") and cleared.
Each pass reconciles with Paper's ledger: shares the account no longer holds (the operator sold them, a
buy stop or the loss limit's Auto sell did) leave the position, said once. A short's buy stops cover what it held: when shares
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
  no key to turn on; a read that fails keeps the names last read that day and `watcher.feed` says why) -- and
  every host with settings or positions, in the feed's
  order. `face` is the followed traders' photo path, or null. `events` are the host's newest
  `live_trader` audit lines (8), read from the audit file's last MB (`LT_AUDIT_TAIL_BYTES`) and again only when
  the file changed. `today.pl_usd` is realized plus unrealized at the last, from the bot's own
  fills; `series` its points at each fill.
- `GET /api/bot/live-traders/asks` answers `{schema_version: 1, generated_at, asks: [{...an ask, host,
  seconds_left}], held: [{host, symbol, side, qty, state}]}` from memory only: every desk window polls it for
  the asks' toasts, and the Bot switch reads `held` before it asks to sell.
- `PATCH /api/bot/live-traders {sell_all_at}` and `PATCH /api/bot/live-traders/{name} {key?, entry?, exit?,
  step_usd?, adds?, allowance_usd?, sides?, short_stop_pct?, take_open?}` answer the view; a value out of
  bounds is 400 `LIVE_TRADER_INVALID` with `field`, never clamped. `key: false` sells nothing: the host's
  bot places no order until it is on again (2026-10-15; it used to sell them). Each change is a `live_trader` `settings`
  audit line `{host, from, to}`.
- `POST /api/bot/live-traders/{name}/asks/{ask_id} {approve: bool}` answers the view; an ask that expired,
  was answered or was withdrawn (the host closed) is 409 `LIVE_TRADER_ASK_GONE`. An approved step meets
  every rule again on the next pass before it is sent.

**Orders** (ADR 055 decision 5): every one through `execution.service.execute`, `origin: "live_trader"`,
`setup: "live_trader:<NAME>"`, an idempotency key unique to each send (`bot:lt:paper:<row id>:<step><n>:<ms>`:
the same trade can be taken again after the host comes back on air, and a reused key would replay the earlier
send's receipt). A long entry or add
is a `place` BUY `LMT` at the ask plus `LT_ENTRY_OFFSET_USD` (2 cents; the last when no ask), source `bot`,
`expected_venue: "paper"`; a short one a `bracket` SELL `LMT` at the bid less 2 cents while SSR is off, and at the ask, which must be over
the bid, while SSR is on or unknown (`short_sale.ssr.live`, as the setup bot prices it; no ask over the bid is
`LT_NO_QUOTE`'s wait) with `short_entry` and a BUY stop `short_stop_pct` over
it, no target. A short step -- an entry or an add -- the one short check refuses only for IBKR's borrow read
(stale, none, unknown) waits `LT_WAIT_SEC` for a fresh read, asked of IBKR at once, before it is a skip -- one the
operator approved (Entry: You) keeps that yes through the wait and is sent once the read comes, never asked again
(Codex review, PR #1025) -- the yes is spent then: the same trade taken again later (sold off air, back on the bar)
is asked for again (Codex review, PR #1026); and every
stock the bot holds short has its borrow read again before it goes stale (`shortability.refresh_due`, as an open
Trader tab does), so the host's add finds it fresh (2026-10-16: an add 72 s after the short met a read 75 s old and
was skipped). Working after the Paper sleeve's `working_ttl_sec`, it is cancelled. A close cancels the
position's buy stops (source `cancel_working`) and sends the protective flatten (source `flatten`, the
practice market ticket) for the bot's shares, never more than the account holds; both name
`target_venue: "paper"`. `live_trader` is one of the door's Nova-close origins on Paper and Sim only
(`execution.md`, "Who sent it").

**Lines.** `ibkr.ticks.set_owner_symbols("live_trader", ...)` holds a Level 1 line on every stock the bot
holds, is entering or waits to enter; never a Level 2 line (ADR 055 decision 3).

**Audit** (the bot's stream): action `live_trader`, outcome `order` (a step sent) | `partial` (a step or close
filled in part: "Fills on the bot audit stream" below) | `filled` | `closed` (a
close sent) | `skipped` | `asked` | `answered` | `refused` (the door's words) | `settings` | `note` |
`error`; `inputs: {host, row_id, symbol, side, step, qty, limit, stop, order_id, code, why, change: {kind:
"open" | "add" | "already_open" | "close" | "trim" | "off_air" | "hidden" | "sell_all" | "stale_day" | "outside", ts, price}, late_sec, venue: "paper"}`. `late_sec` is the send's wall time less the feed's
time of the change. A skip is written once per position, step and code. Codes: `LT_FEED_BEHIND`,
`LT_FEED_DOWN`, `LT_TICKER_UNSETTLED`, `LT_MISREAD`, `LT_OPEN_TOO_FAR`, `LT_SMALL_CAP`, `LT_CAP_UNKNOWN`, `LT_NO_QUOTE`,
`LT_ALLOWANCE`, `LT_ADDS_DONE`, `LT_SHORTS_OFF`, `LT_AGAINST`, `LT_NOT_HELD`, `LT_VENUE`, `LT_BOT_OFF`,
`LT_FROZEN`, `LT_AFTER_SELL_ALL`, `LT_SHORT_HOURS`, `LT_NOT_PRICEABLE`, `LT_ASK_EXPIRED`, `LT_ASK_SKIPPED`,
`LT_ALREADY_OPEN`, `LT_OFF_AIR`, `LT_HIDDEN`, `LT_LOSS_LIMIT`, `LT_NOT_ON_BAR`, `LT_OTHER_HOST`, `LT_ROW_UNREAD`,
`LT_ADD_IMPLAUSIBLE`, `LT_ADD_IS_SALE`, `LT_NO_CLOCK`, `LT_FAMILY_OFF`, `LT_KEY_OFF`. Lines written before 2026-10-15 may carry the
retired change kinds `key_off` and `bot_off` (a key or the Bot switch turned off sold everything then). `LT_BLANK_BAR` and `LT_RETURN_SWITCH` are waits, said as `note` lines
(`step` `blank` for a held sell, `lt_blank_bar` / `lt_return_switch` for a held take), never skips.

**The Bot switch** counts a host key on as a strategy On on Paper (`BOT_NO_SETUP_AT_STRATEGY`: "no
strategy is On and no Live Trader key is on"); `GET /api/bot/session`'s `setups` gate adds
`live_traders: [NAME]`. OFF -- the Bot switch's, the LiveTrader Bots key's or a host's -- sells nothing, and the
bot places no order while it is off ("The three keys").

**On the desk.** The section's cards (mockup v1, approved 2026-10-14): the host's photo or initial, on air
and how old the read is, the key, Entry You | Bot and Exit You | Bot with the mode in words, the allowance
bar, today's P/L, trades and skips with a line of the day's P/L, the positions (shares, the bot's cost, the
host's average, now, P/L), the last events with their reasons, and the settings as chips that open their
editors. A line above the cards says what stops every host now (`can_trade.why`). An ask is a line on its
card and a toast in every desk window (`bot/BotNotices.tsx`) with Skip and Approve and its seconds left. A host
whose key is off while its bot holds positions reads "Key off · no orders: N held, not sold until it is on".

## Fills on the bot audit stream (operator ask 2026-10-16)

"Do we have a way to get out of persistent event stream for partial fills, full fills, and failures when
bots enter or exit trades?" The stream was there -- `bot-audit.jsonl` in the operator cache, read by
`GET /api/bot/audit?limit=` and pushed live on `/ws/bot/audit` (loopback only; a snapshot of the last 50,
then each line) -- but an order that filled in parts wrote nothing until it ended, and the outcome names
were whatever each caller typed.

- **Fixed outcome names.** A bot trade line -- action `bot_trade`, `buy_setup_limit` or `short_setup_limit`
  (Nova's own bot) or `live_trader` (the Live Trader bot) -- carries one outcome of `BOT_TRADE_OUTCOMES`
  (`constants_bot.py`): `ok` (an entry sent), `failed` (an entry refused), `order` (a Live Trader step
  sent), `partial`, `filled`, `half`, `closing`, `closed`, `missed`, `handed`, `skipped`, `asked`,
  `answered`, `refused`, `settings`, `note`, `error`. `bot.audit.record` logs an error for any other name
  on those actions and still writes the line (a line is never dropped); a test holds every name the two
  bots write to the set. Other actions' outcomes (`level`, `venue`, `hot_list`, ...) are unchanged.
- **`partial`.** Each time a working order of a bot -- Nova's own bot's entry, a resting target or stop,
  or its close; a Live Trader step or close -- shows more filled shares than were last said, one `partial`
  line: `order_id` the order's, `reason` in words ("bought 40 of 100 PLTR at 25.10, 60 still working"),
  and a top-level `fill: {phase: "entry" | "exit", leg, order_id, qty, filled_qty, remaining_qty,
  avg_fill_price, status}`. `leg` is `entry` | `target1` | `target2` | `stop` | `close` on Nova's own bot
  and the step (`open`, `add`, ...) or `close` on the Live Trader. `remaining_qty` is the venue row's, or
  `qty` less `filled_qty` when the row has none; `avg_fill_price` is null when the venue has not priced it.
  The order's end is still the line it always was (`filled`, `half`, `closed`, `missed`, ...), counting
  the shares that filled. A partial line never counts toward the daily entry cap.
- **`fill` on the full fill.** The line that ends a fill carries the same block: Nova's own bot's
  `filled` (its entry), `half` (target 1 selling its part) and `closed` (the target, stop or close that
  sold the last shares; none when the shares left outside the bot), and the Live Trader's `filled` (a step
  or a close).
- **Owner and invalidation.** `bot/fill_progress.py` keeps the filled shares last said for each working
  order, in memory, keyed by the order id and the venue row's own placed stamp (a Sim rewind can hand an
  id out again), and drops it when the order ends. A process start forgets them: an order still working
  that had filled part before the start is said once more, with the same numbers.
- **Where partials come from.** Paper and Sim fill an order whole, so no `partial` line appears there
  today; the rule reads the venue's order row, so it holds on any venue that fills a bot's order in parts.
