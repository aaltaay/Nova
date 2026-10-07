# Data schema: Setup scanner, templates, eyes, tape flow and signal trials

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/setup_scanner/, backend/setup_templates/, backend/eyes/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Setup scanner and tape gate (ADR 022)

`GET /api/setups/board` and the `{"type": "board", ...}` frames of `/ws/setups`
(owner `backend/setup_scanner/`; read-only -- nothing there places, stages or
cancels an order) answer `schema_version: 1`, `generated_at`, `session_date`
(Eastern `YYYY-MM-DD` or null), `universe` (symbols followed: the HOD Momo
active set), `universe_symbols: string[]` (those symbols, sorted -- added
2026-09-24 for the watch list; a Sim eyes board lists its replay's symbol),
`seeding` (symbols still loading today's bars, IBKR's history included -- below), `scoreboard:
boolean`, `scoreboard_error: string | null`, `proposing: boolean` (false on a
replay desk), `rows[]` (at most `SETUPS_BOARD_MAX_ROWS`; near, armed, triggered
within 30 min, pullback, leg, failed within 5 min, then nearest the trigger)
and `proposals[]` (the open ones). A row is `{symbol, state: "watching" |
"leg" | "pullback" | "armed" | "near" | "triggered" | "failed", reason, kind:
"first_pullback" | "second_pullback", nth, setup_id: string | null, setup:
{leg_t, trigger, entry, stop, risk, target1, pullback_bars, leg_high,
leg_low, leg_pct, armed_bar_t, armed_at, kind, triggered_at?, trigger_price?,
nth?} | null, leg: {t, high, low, pct} | null, last_price, distance: number |
null (trigger minus last, armed and near only), grade: "A" | "B" | "C" | null,
pillars: {price, change_pct, rvol, float, float_contradicted,
shares_outstanding, float_note, news, headline, catalyst} | null, tape:
{verdict: "go" | "wait" | "veto" | "blind", reasons: string[], line, metrics}
| null, proposal | null, outcome: "target_first" | "stop_first" | "open" |
null, bar_r, mfe, mae}`. An unknown pillar is `null`, never a failed one, and
no frame carries a bare `NaN` (`scanner_wire`). `float_contradicted` /
`shares_outstanding` are HOD Momo's float check (#532): a contradicted float's
pillar passes only on shares outstanding at or under the pillar's limit and is
otherwise `null`, and `float_note` (`string | null`, set at arm time with the
template's limit) says which; a template's stock filter reads the float by the
same rule and keeps out a contradicted float it cannot rescue, even with
`unknown_passes`. A proposal is `{id, setup_id,
symbol, kind, trigger, entry, stop, target1, risk, grade, reasons, created_at,
status: "open" | "triggered" | "failed" | "disarmed" | "rearmed", tape_now}`
-- raised only when a live setup is `near` and the tape says `go` (a re-arm at
new levels withdraws the open one, and the next `go` raises a fresh one), pushed once as
`{"type": "alerts", "alerts": [...]}` and recorded on the bot audit stream as
`setup_proposal` / `proposed`. Its close is recorded there too (a re-arm
replaces the engine's own copy): `setup_proposal` with outcome `rearmed` |
`disarmed` | `failed` | `triggered`, `reason` the plain-words cause, and
`inputs` the proposal with its `status` and `closed_at` -- the Bots page lists
the last half hour's withdrawn proposals from it. `blind` means Nova holds no
depth line for the symbol; the scanner opens none.
`GET /api/setups/scoreboard?days=N` (default 5, `0` = all) answers `{days,
date_from, row_count, rows[] (at most 500), summary: {all, by: {tape_at_trigger,
grade, session, kind}}}`, each stats block `{armed, triggered, trigger_rate,
target_first, stop_first, open, scored, win_pct, avg_r, avg_net_r, avg_mfe_r,
avg_mae_r}`; `GET /api/setups/rows?date=YYYY-MM-DD&symbol=` one day's rows.
Both answer 503 with the reason while the store is not open. Rows live in
`setups.db` under the operator cache (SQLite, `PRAGMA user_version = 1`; an
unknown version, or an unversioned file that already holds the table, refuses
to open and the board reports `scoreboard_error`), one per armed setup: levels,
grade and pillars at arm time, `near_tape` / `trigger_tape`, the first touch,
MFE / MAE over 15 minutes and `bar_r` under the research exit rules --
scores, never fills.

**A symbol followed mid-session is seeded from 04:00** (2026-10-02: AMOD, followed at 07:51:22
after trading since 04:00, wrote its first first-pullback line at 08:23, 32 bars later). Owner
`setup_scanner/seeder.py`. The bar store holds a symbol's minutes only once a chart fetched them or its
Level 1 line built them, so a name admitted mid-morning had nothing before its line opened. When the
stored minutes start more than `SETUPS_SEED_LATE_START_SEC` (10 min) after 04:00, or there are none, the
symbol stays `seeding` while IBKR's 1-minute history of today is asked for (`hooks.live_history`: the
charts' paced `historical_service.request_bars`, background priority, on the IB loop; nothing is asked
when IBKR filled today's minutes and the stored ones start by then). Requests are asked one symbol at a time, oldest
first; at most one every `SETUPS_SEED_HISTORY_SPACING_SEC`; never while a chart's history loads; only
while fewer than `SETUPS_SEED_HISTORY_BUDGET` (30) of IBKR's 60 per 10 minutes went out. Then the
symbol is seeded from the store again. The Level 1 line's minutes since the follow keep their place,
so no minute counts twice. The minute now forming is never seeded. A name that leaves the followed set
keeps its place in the queue. History that does not come (two unanswered asks, or 10 minutes) is given
up, and the symbol is seeded with what the store has, as before. A hole later in the day is seeded as it
is: waiting would hold a name whose lanes are warm out of the open. The wire is unchanged.

**The tape at a trigger is the tape Nova saw** (operator report 2026-09-30:
"why didn't we trade it?" -- LGHL's first pullback triggered at 07:16:10 and
read WAIT, "burst of red", while 7.9k shares lifted the offer through the
trigger). A lane reads the tape for a setup coming `near` and for a trigger at
the moment it handles that price -- its host's clock, never before the price's
own stamp (`Lane.read_at`) -- and a read takes every print received before it
(`TapeFeed.prints` drains the print queue first). The L1 last carries IBKR's
whole-second trade time while prints carry their arrival (#563), so a read
that ended at the stamp left out the prints that crossed the trigger: on the
Session Record, LGHL reads WAIT at 07:16:10.000 (1,454 shares at the bid, none
at the ask) and GO at 07:16:10.856, when the trigger arrived (124 prints,
7,882 shares at the ask). A replay already read at the end of the price's
second. Every tape read's `metrics` adds `read_at` (epoch seconds its window
ends at): a `setups.db` row without it read the earlier window, and nothing
stored is rewritten. `triggered_at`, the scoring and a trigger's age keep the
price's own stamp; that stamp's lag is #667.

**Every setup's scanner (ADR 031, operator decisions 2026-09-24).** The bull
flag, the flat-top breakout and red to green get detectors beside the first
pullback's (`setup_scanner/bull_flag.py`, `flat_top.py`, `red_to_green.py`;
rules pre-registered in ADR 031), on the same ladder of states, the same tape
gate and the same scoring; since 2026-10-02 Gap and Go too (`gap_and_go.py`, the
research's A2 rule, ADR 031 amendment: the pre-market high, armed at the 09:30
open when the open is under it, broken by 10:00, stop `min(20c, 4%)` under the
entry, one try a day; a new setup starts Off on every venue); since 2026-10-06 the 5-minute flat top
(`flat_top_5m.py`, "The 5-minute flat top" below). The board is `schema_version: 2`: every row and
proposal adds `setup_type: "first_pullback" | "bull_flag" | "flat_top_breakout"
| "flat_top_5m" | "red_to_green" | "gap_and_go"`; a row adds `failed_at: number | null` and its `setup` adds
`detail: object | null` (the setup's own facts: `entry_mode`, `broke_at` and the touches for
the flat-top breakout ("The flat top counts its touches" below), `open` and `red_bars` for red to green, `pole_bars` for the
bull flag, `pm_high`, `pm_high_t`, `open`, `open_t` and `stop_rule` for Gap and Go);
`kind` is one of `first_pullback | second_pullback | bull_flag |
second_bull_flag | flat_top_breakout | second_flat_top_breakout | flat_top_5m |
second_flat_top_5m | red_to_green | gap_and_go`
(the kind without `second_` is the first of that setup on that symbol that day);
`leg` is the setup's context (`{t, high, low, pct, bars?}`: the leg, the pole, the
impulse into the high of day, the open and the red phase, or Gap and Go's
pre-market high with `low` its stop); rows are capped
per setup (`SETUPS_BOARD_MAX_ROWS` each). The top-level `template` /
`templates_watched` move into `setups[]`, one entry per setup with a scanner:
`{id, level: 0 | 1 | 2, chosen: boolean, proposing: boolean, template: {id, rev,
name, params_hash} | null, templates_watched, window: {start, end, state:
"before" | "open" | "after"}, counts: {watching, forming, armed, near,
triggered, failed, filtered, proposed}}` -- `forming` counts the symbols now in
`leg` or `pullback`, the rest count today's rows (`proposed`: rows that raised a
proposal). The top-level `proposing` is true when any setup proposes. A setup
proposes only at effective Eyes or above (ADR 042: the lower of the master
`level` and its own `setup_levels[setup]`; the board's `setups[].level` is the
effective level and `chosen` is always false, kept one release); at Off it
watches and scores, silently. A proposal the bot or Auto-entry will take carries
`taken_by: "bot" | "auto_entry"`, one that is not a trade `not_a_trade:
{reasons}` (and `grade`, `pillars`, `spread`); both are still raised, and the
desk locks their Stage with the reason. `setups.db` is schema 3: rows add `setup_type` and `detail`
(JSON); a schema-2 file migrates in place, its rows the first pullback's (schema
1 migrates through 2); row ids keep their form for the first pullback and add
`@<setup_type>` for the others, before any `~TEMPLATE_ID` (a later setup on a key
whose row holds a trade adds `#N` to the key: "One row per trigger" below). `GET
/api/setups/scoreboard` and `GET /api/setups/rows` take `setup=` (default
`first_pullback`) and answer for that setup's template in play; both add
`setup_type` to their answer. `GET /api/setups/rows?setup=all` answers every
setup's template in play at once, oldest armed first (the Bots page timeline;
with `template=all`, every template's rows).

**The grade you can see (operator report, 2026-09-29).** "So why does it think
this is a good trade when it's obviously not?" -- AVAT's first pullback
triggered at 08:06 on one pillar of five (grade C), and the Trader's plan still
read TRIGGERED twenty minutes after its stop printed. The % change pillar was
unknown on 17 of 43 first-pullback arms and 20 of 42 flat-top arms since 09-23:
HOD Momo's snapshot carries a change only when its IBKR snapshot returned a
prior close. `setup_scanner.grade.read_pillars` now measures it from the
scanner board row's `prev_close`, else the L1 line's tick-9 prior close, when
the snapshot has none (`null` when neither knows). Board rows and `GET
/api/setups/symbol/{symbol}` lanes add:
- `graded: "armed" | "forming" | null` -- where `grade` / `pillars` come from:
  the setup's arm-time read (`armed`), or, while the pattern is forming (`leg`
  / `pullback`) with no setup armed, the read taken when its current leg made
  its high (`forming`: the lane reads the pillars on each `leg` event and the
  `leg` journal line carries them as `grade` / `pillars`).
- `phase: "armed" | "near" | "triggered" | null` -- under a `filtered` row,
  where the pattern itself stands (`null` on every other row). A `filtered` row
  stays on the board while its pattern is armed or near, and for 30 minutes
  after it triggered (the triggered rows' window), no longer five minutes from
  its arming; its `distance` is set while armed or near. It still reads no tape,
  never proposes, is never scored and never reaches the bot. Its re-arm is
  journalled (`rearmed`, the new levels), and a `state` line that says
  `triggered` carries `triggered_at`, so a playback draws the same row.
- `trigger_tape: {verdict, reasons} | null` -- the tape gate's read at the
  trigger (`null` before one, and on a filtered setup).
- `outcome_at: number | null` -- when the scoring's first touch (target 1 or
  the stop) printed; `scored` journal lines carry it.

## The flat top counts its touches (ADR 031 amendment, operator ask 2026-10-06)

"Make it something special like this ... when it starts forming. I doubt real life is going to be perfect as this, so
we may need a drift or a ratio to still consider flat top." Owners `setup_scanner/flat_top_shape.py` (the shape, pure),
`setup_scanner/flat_top.py` (the states); on the desk `frontend/src/stock_read/flatTopShapes.ts`.

- **The rule.** The level is the high of day.
  - A **touch** is a candle whose high is within the tolerance under it: `ft_touch_pct` of the level (0.5%) or
    `ft_touch_dollars` ($0.01), whichever is more. A candle a little over the earlier touches, inside the tolerance,
    is a touch too: the level drifts up to it and keeps its row.
  - The base runs from the **first touch**, the earliest candle in the zone after an impulse into it. Every later
    close stays within `ft_band` under the level and every low on the EMA.
  - At least one touch after the first makes no new high (a retest): highs rising a cent at a time are a move.
  - It is drawn forming from its second touch (state `leg`, `forming.waiting: "N more touch(es)"`, `forming.bars` the
    touches). It arms at `ft_min_touches` (3) on a base of `ft_min_consol`-`ft_max_consol` (2-20) candles. A flat top
    that began longer ago is stale.
  - The hold entry reads the zone as the level: a candle whose low stays in it and that closes green over the high
    holds. Only a close under the zone fails it.
- **The research's P2 is a setting.** `ft_base_start: "last_high"`, one touch, no tolerance and a 6-candle base
  (`flat_top_shape.P2_RULE`) run it exactly. A stored template without the new parameters reads `catalogue.LEGACY`
  (P2's values), never the new defaults. The catalogue's tables moved to `setup_templates/params.py`; `catalogue.py`
  keeps the validator.
- **Revisions.** The built-in default's revision is per setup (`SETUP_TEMPLATE_DEFAULT_REVS`, `setup_default_rev`): the
  flat top's is 2 and its read-out starts over. The 5-minute flat top became a strategy of its own the same day
  ("The 5-minute flat top" below).
- **On the wire.** A flat top's `leg` adds `touches: [[t, high], ...]` (oldest first) and `zone` (the lowest high that
  touches), and `bars` counts the base. Its armed `detail` adds `touches`, `zone`, `min_touches` and `broke_bar_t`
  (the break's candle, hold entry). A triggered hold adds `hold_bar_t` and `hold_high`. A row, journal line or
  episode written before has none of them.
- **On the desk.** The drawing follows the operator's sketch:
  - a violet level from the first touch to the right edge, dashed while it forms;
  - a ring on each touch, the last ring counting them ("4 touches", "2 of 3 touches");
  - the base boxed;
  - a green triangle over the candle that broke it, and a green box around the candle that held it;
  - its name in the edge column ("FLAT TOP = HOD 5.50" until it breaks).

  A flat top that is not the plan's lead is a dimmed violet without labels, and a failed one is grey. A past flat top
  keeps its rings, faint. The 5-minute flat top draws the same way on the 5-minute chart, and its trigger line reads
  "5m FLAT TOP". Every pane's Key adds the flat top's marks.
- **Unchanged.** The 1-minute flat top plays as before. No flat-bottom short: Nova opens no shorts (Invariant 7).

## The 5-minute flat top (ADR 031 amendment, operator ask 2026-10-06)

"Make the 5-minute flat top a Paper buy with a 1-minute hold entry, as the material trades it." The material reads
the flat top on the 5-minute chart and buys the 1-minute pullback that holds it after the break. Owner
`setup_scanner/flat_top_5m.py`; on the desk `frontend/src/stock_read/flatTopShapes.ts` and `fiveMinuteShapes.ts`.

- **A sixth strategy**, `flat_top_5m`: its own Off / Eyes / On per venue (starting Off), templates, read-out (kind
  `flat_top_5m` / `second_flat_top_5m`), bot rules and window, like every setup. Nova's bot buys it at On, on Paper
  and Sim only.
- **A 1-minute lane, a 5-minute pattern.** Its lane is fed the scanner's minutes, so the tape gate, the liquidity
  check, the scoring and the bot are the minutes'. Its detector makes 5-minute candles of them
  (`five_minute.candles`; one is over once its last minute or a later one is in) and reads the flat top on those by
  the flat top's own rules ("The flat top counts its touches" above): `bar_sec` 300, arming 07:00-15:30.
- **The entry is the 1-minute hold.** After a price over the flat top, it is the first of the next `ft_hold_bars` (5)
  minutes after the break's own that holds the touch zone and closes green over the high. Entry is one cent over its
  close, the stop is the pullback's low (`ft_hold_stop`: `pullback`, or `candle` for the hold minute's low), and the
  dollar caps read that risk. A minute closing under the zone fails it. It is scored on 1-minute candles from the
  hold minute. Its rows carry no 5-minute read (`tf5_*` null): its pattern is that chart, and trial T8 reads
  1-minute setups.
- **The built-in 5-minute flat-top lane is gone** ("The 5-minute setups" below keeps the first pullback and the bull
  flag), and auto-record's setups window now runs to 15:30 ("Auto-record" above).
- **On the wire.** It comes in the stock read's and the symbol view's `setups` with `timeframe: "5m"` and `rules`
  adding `hold_bar_sec`. Its `detail.broke_bar_t` and `hold_bar_t` are minutes. The past setups at `?tf=5m` fold its
  lines; `?tf=1m` leaves them out.
- **On the desk.** The 5-minute chart draws it as the flat top, its hold named "1m hold" in its 5-minute candle.
  Once it arms, the 1-minute chart draws its level from the first touch, the break and the hold minute. At Off it
  draws nothing, like every strategy.

## One row per trigger (ADR 022 amendment, 2026-10-02)

AMOD's first pullback triggered at 08:48:04 and was stopped at 08:48:13. At 08:49 a candle tied the
leg's high, and the detector armed the same leg again as the second pullback. The lane named rows by
the leg, so it wrote the new levels and `kind: second_pullback` over the trade's row
(`AMOD-2026-10-02-1790945160`), and the read-out, which counts the first of the day, lost the trigger.
A row is one setup up to its trigger and the trade after it (owner `setup_scanner/lane_ids.py`):

- **A later setup on a key gets its own row.** An arming on a key (the leg, the pole, the base, the
  open) whose row holds a trigger opens `SYMBOL-DATE-KEY#N`: N is the attempt on that key (2, 3,
  ...), then `@SETUP` and `~TEMPLATE_ID` as before. The first attempt keeps the id it always had.
  Nothing arms, re-levels or triggers a row that holds a trigger.
- **Readers keep treating the id as opaque.** The board, the symbol view, the scoreboard, the
  read-out, the triggers audit, the Sim playback, the past setups and the bot only match ids, and
  none parses one. A trigger event and its proposal carry the new row's id, so an Approve given to
  the first attempt never sends the second.
- **A restart never writes over a trade.** A lane making a symbol's detector asks `setups.db` which
  of today's rows on that symbol hold a trigger (its template and setup) and leaves those ids alone.
- **A detector made mid-day remembers the day.** That happens after a restart, when a symbol leaves
  the universe and comes back, or when a template is edited. The detector starts from the day's
  triggers on its symbol in that lane, from memory, else from `setups.db`. A later setup then reads
  as the second, the setups-a-day cap holds, and red to green's one try stays spent: GOW
  (2026-09-30) triggered twice on one id after its detector was made again.
- **Rows written before keep their ids and are not repaired by this change.**

## Too thin to trade (ADR 022 amendment, operator decision 2026-10-01)

"There's no way I will ever trade something like that with a 20-cent spread ... the volume is almost
dead": LPA, Gainers #41 at +10%, armed five setups and drew them like trades. It had traded $1.0M all
day by its first trigger and $42K in the five minutes before it, with 100 shares at the inside and the
next offer 18 cents up. Owner `setup_scanner/liquidity.py` (pure; constants `SETUPS_THIN_*`). A stock is
**too thin** at a moment when any check fails:

- **day**: under $2M traded today (from 04:00 ET), measured as the day volume times the volume-weighted
  average price of its minutes;
- **pace**: under $100K traded in the last five closed minutes;
- **book**: with a Level 2 book and a size (the desk venue's risk per trade over the setup's risk a
  share), buying that size walks the asks more than 0.25R past the best ask.

A check Nova cannot make is unknown -- never thin, never a pass. A **reading** is `{state: "ok" | "thin"
| "unknown", reasons: string[], failed: ("day" | "pace" | "book")[], unknown: {day?, pace?, book?: string},
day_dollars, pace_dollars, pace_sec, walk: {qty, best_ask, last, avg, over_ask, shown, short, r} | null,
as_of, limits: {day_dollars, pace_dollars, walk_r}}`; `ok` needs the day and the pace both known.

- **The lanes** (`setup_scanner/lane_liquidity.py`) read the active setup:
  - when it arms, when it first comes near, at each closed minute while it is armed or near, and at its
    trigger, from the lane's one-minute bars, the day volume in its pillars, the host's newest fresh
    book and the desk's risk per trade (`LaneHost.risk_usd`, the venue sleeve's, re-read every
    `SETUPS_THIN_SIZE_TTL_SEC`; a replay has none and never judges the book);
  - the pillars add `volume` (shares today: HOD Momo's snapshot live, the leaderboard row on a replay).
- **On the wire.** Board rows and `GET /api/setups/symbol/{symbol}` lanes add `liquidity: reading |
  null` -- the armed setup's, frozen at its trigger; null before it arms, on a filtered setup, and from
  rows stored before.
- **What it changes.**
  - A thin setup never proposes.
  - Its trigger event adds `liquidity`, and NOT A TRADE (`trade_verdict`) adds "too thin to trade: ..."
    for the bot, Auto-entry, Approve and the plan.
- **The journal.** The `armed`, first `near` and `triggered` lines carry `liquidity`, and a `liquidity`
  line records a changed verdict between them, so the Sim playback folds the same rows.
- **The store.** `setups.db` is schema 5: rows add `liquidity` (JSON, the reading at the trigger once
  it triggered). A schema-4 file migrates in place, and its rows read unknown.
- **The read-out** leaves a setup thin at its trigger out of both pools and adds `thin_left_out:
  integer | null`. The scoreboard summary's `by` adds `liquidity` (`ok` | `thin` | `unknown`).
- **The stock read** (`stock_read/plan_liquidity.py`) reads the stock now, from the read's volume, the
  chart's stored minutes and the Trader's Level 2 walked for the plan's risk. Minutes that end more
  than `SETUPS_THIN_BARS_STALE_SEC` ago leave the pace unknown.
  - The Plan adds `liquidity: reading | null`, and its `checks` start with `liquidity`.
  - The In play group adds the row `liquidity` ("Liquidity": "Too thin" / dollars / "Not known"), and
    its tile reads "Too thin" when thin.
- **On the desk**, a thin setup is greyed, never hidden:
  - the setup cards and the Setups board add a "Too thin" chip with the reasons and the rule on hover;
  - the plan reads TOO THIN;
  - the 1-minute badge reads "SETUP · TOO THIN TO TRADE", with no track and no call to enter, even after
    it played out;
  - the charts draw no plan for it (no zones, no plan-only lines, its lane faded) and Level 2 marks no
    plan level. A level an order stands behind is still drawn.

## The 5-minute chart on a 1-minute setup (trial T8, operator decision 2026-09-30)

"Sometimes the 1-minute setup aligns well with the 5-minute setup ... I want to make sure we are utilizing
all of that"; on the choice: "Show it and test it". Owner `setup_scanner/five_minute.py` (pure). A **5-minute
read** is `{agrees, above_ema9, macd_up, close, ema9, macd_hist, candles, as_of}`: 5-minute candles made on
the clock from 04:00 ET of the scanner's own closed one-minute bars (a candle counts once its five minutes are
over; five minutes without a bar make none), `above_ema9` the last complete candle's close over the 9-period
EMA of the 5-minute closes, `macd_up` the 5-minute MACD (12, 26, 9) histogram over 0, `agrees` both; the EMAs
seed with the first close (`series.ema`), `as_of` the last complete candle's start. `null` before the first
5-minute candle is complete. Every lane reads it at each closed minute:
- Board rows and `GET /api/setups/symbol/{symbol}` lanes add `tf5: read | null` and `tf5_at: "trigger" |
  "armed" | "forming" | null` -- the read at the trigger once the setup triggered, else when it armed, else
  (forming, no setup armed) when its leg made its high. The `leg`, `armed` and `triggered` journal lines carry
  `tf5`, so the Sim playback draws the same row.
- `setups.db` is schema 4: rows add `tf5_armed` and `tf5_trigger` (JSON); a schema-3 file migrates in place,
  its rows read as unknown. The scoreboard summary's `by` adds `tf5_at_trigger` (`agrees` | `against` |
  `unknown`).
- The stock read's plan adds a check `{id: "tf5", state: "info", text: "5m agrees: over its 9 EMA 16.95, MACD
  up (trial T8)"}` -- the 5-minute chart now, from the read's own session minutes by the same rule.
- On the desk the Bots page's setup cards and Watchlist › Setups add a **5m** column: "5m ✓" (green) or
  "5m ✗" (grey, never a warning colour), the hover saying which part failed, when it was read and that it is
  in trial. Nothing places, stages, gates or blocks on it.
- In sample (the harness's 1,050 bar-level trades, `F:\Nova\eyes\studies\mtf-alignment-2026-09-30`) it
  leaned the right way and did not hold: pooled +0.10R (95% CI -0.08 to +0.28), and the agreeing trades still
  lost (-0.27R). Trial T8 (`knowledge/signal-trials-3.json`, "Signal trials" below) decides whether "5m
  against" ever becomes a warning.

## The 5-minute setups (operator decisions 2026-09-30)

"We need 5-minute strategies ... sometimes I see slow stocks moving upwards, and you can see clear patterns in
the 5-minute chart, but they're not clear in the 1-minute chart"; on the IOVA mockup: build it this way, chart
only, a chip and the trigger line on the 1-minute, arming 07:00-15:30. Owner `setup_scanner/five_minute_lane.py`.
- **The lanes.** One built-in lane per setup in `SETUPS_5M_SETUPS` (the first pullback and the bull flag; the flat
  top's became a strategy on 2026-10-06, "The 5-minute flat top" above) runs beside the template lanes: the setup's own detector on 5-minute candles made of the scanner's
  minutes (`five_minute.candles`: on the clock from 04:00 ET, complete once their five minutes are over). The
  detector reads only when a candle completes, and a price inside a forming candle carries that candle's open.
  Its rules are the default template's except:
  - `bar_sec` 300, arming until 15:30 (`SETUPS_5M_ENTRY_CUTOFF_ET`);
  - a risk up to 6% of the entry (`stop_cap_pct`: the 2026-09-29 study's 5-minute rule; every detector's risk
    check reads `detector.stop_cap`);
  - the scoring exit counts 5-minute candles, and the first touch, MFE and MAE are read over 60 minutes
    (`SETUPS_5M_SCORE_WINDOW_MIN`).

  Template id `5m` (rev 1, name "5-minute", `params_hash` over those rules): its scoreboard rows end `~5m`, so
  no read-out, trial (T7, T8) or bot reads them, and a setup's `templates_watched` never counts it.
- **It never plays.** A 5-minute lane raises no proposal, tells the bot nothing, and has no Setups board row
  and no Bots page card. It reads the tape gate and scores like any lane. Its journal lines carry `template:
  "5m"` and `playing: false`, and the Sim playback leaves it out of a setup's counts.
- **The wire.** `GET /api/setups/symbol/{symbol}` adds `setups_5m` (the built-in 5-minute lanes, shaped like
  `setups`, `level` 0, `chosen` false), and every lane adds `timeframe: "1m" | "5m"` (the candles its pattern reads:
  the 5-minute flat top in `setups` is `5m`); `rules` adds `stop_cap_pct`, `bar_sec` and `hold_bar_sec`. The stock
  read adds `setups_5m` (never a plan's lane). `GET /api/stock-read/{symbol}/past-setups?tf=5m` folds the 5-minute
  lanes' lines and the 5-minute flat top's (`EpisodeFold("5m", 300)`: the candle a line is about is a 5-minute one), measures what came after over 60 minutes and adds `timeframe`; a
  `tf` other than `1m` or `5m` is a 400.
- **On the desk** (`frontend/src/stock_read/fiveMinuteShapes.ts`; a live lane's drawing moved to
  `laneShapes.ts`, which with `pastShapes.ts` takes the candle's length):
  - The 5-minute pane draws the 5-minute lanes as the 1-minute pane draws its own. The most advanced is in
    colour; the rest are faded, and their labels make room. The ones that ended stay faint, with how they
    ended and what came next. Every label starts "5m", and the lead's trigger, stop and target are dashed
    lines with axis labels. A hover card is titled "5-minute".
  - The 1-minute pane shows a built-in 5-minute setup armed or near its trigger as a legend chip ("5m bull flag ·
    near 13.80") and one dashed trigger line, nothing else.
  - Each pane's Key lists them.
- **What is known.** The bar-level 5-minute versions lost less than their 1-minute twins over five years, and
  still lost (2026-09-29). On IOVA 2026-09-29 the 1-minute scanners saw 33 setups and triggered one. On
  5-minute candles the same rules triggered four: the first touched its target first, two were stop first, and
  one was still open at 10:10. Nothing trades on them; their rows collect the evidence.

## The tape flow score and the flush exit (ADR 034, operator ask 2026-09-24)

"Can my bots detect if we are seeing flush like this so we can exit a position
or burst of greens where we can enter ... just a small piece of the final
decision." Owner `setup_scanner/tape_flow.py` (pure). A **flow reading** is
`{score: number | null, label: "burst" | "flush" | "neutral" | "quiet" |
"blind", readings: {imbalance, pace, drift, book}, metrics: {window_sec,
ask_shares, bid_shares, ask_prints, bid_prints, between_shares, pace_ratio,
baseline_sec, drift_pct, bid_depth, ask_depth, best_bid, best_ask}}`: each
reading from -1 (sellers) to +1 (buyers) and `null` when Nova cannot take it
(no fresh book, a baseline shorter than the window, one price) -- never 0; the
score is the weighted mean of the known readings (`null` with none); `quiet`
is too little tape at the bid or the ask to say, `blind` no print and no book.
Lit prints only (FINRA / TRF / ADF out), a `between` print counts for no side,
the drift reads only prints that set a price, and the baseline never counts
time before the feed could see the tape. Every number is a template parameter
(the catalogue's `flow` group on every setup with a scanner): `flow_window_sec`,
`flow_baseline_sec`, `flow_min_prints`, `flow_min_shares`, `flow_w_imbalance`,
`flow_w_pace`, `flow_w_drift`, `flow_w_book` (not all zero), `flow_pace_full`,
`flow_drift_full_pct`, `flow_book_levels`, `flow_burst_at`, `flow_flush_at`;
and the two choices below, whose defaults are the pre-registered rules.

**Entry** (`tape_entry: "gate" | "score" | "both"`, `flow_entry_min`): `gate` is
ADR 022's print counts; `score` keeps the vetoes and a seller that is not
thinning and replaces the print counts with the score at or over the minimum
(a quiet or blind flow waits); `both` needs both. Every tape read (a board row's
`tape`, `setups.db` `trigger_tape`) adds `flow` (the reading) and
`metrics.flow_score` / `metrics.entry_mode`; `near_tape` and the trigger event
the bot hears add `flow: {score, label}`.

**Exit** (`flush_exit: "off" | "tighten" | "exit"`, `flush_hold_sec`,
`flush_trail_r`, `flush_min_r` nullable): a `flush` at least `flush_hold_sec`
after the entry -- with `flush_min_r`, only while the trade is up that many R --
moves the stop up to `flush_trail_r` R under the price (never down) or gets out
at the bid (`tape_flow.flush_action`). Every lane reads each triggered setup's
flow every `TAPE_FLOW_EVAL_SEC` through its scoring window
(`setup_scanner/lane_flow.py`; the live engine keeps that symbol's tape); the
scoring exit applies the rule (`bar_exit_reason` adds `flush` / `flush_runner` /
`flush_stop` / `flush_stop_runner`; a backtest row adds `flush_action`,
`flush_at`, `stop_now`), and Nova's bot applies the same rule from its own fill
to its trade (`bot/first_pullback/flush.py`; the trade's `exit_reason` adds
`flush`, a tightened stop is a `bot_trade` `note`) from the scanner's newest
reading (`SetupEngine.flow_reading(setup_id)`, never older than
`TAPE_FLOW_READING_STALE_SEC`). The eyes' journal adds `flow` (a turn into or
out of a burst or a flush after a trigger: `label`, `was`, `score`, `readings`,
`price`, `since_trigger`) and `flush` (`action`, `score`, `price`, `bid`,
`stop`, `exit_px`, `mode`). The scoreboard summary's `by` adds
`flow_at_trigger`; a fill count of three covers `flush_runner` /
`flush_stop_runner`. `/sensors/flow` adds `score` (a flow reading with the
default numbers over the sensor rings; `SENSOR_TAPE_RING` 4,000 prints).

**Measuring it.** `eyes/flow_study.py` (`tools/flow_study.py`, read-only) reads
each recorded second through the score and measures the mid's move 10 s to 5 min
later -- never across a gap -- answering `{schema_version: 1, params, study,
recordings, seconds, seconds_by_label, onsets: {burst | flush: {HORIZON: {n,
mean_bp, median_bp, up_pct, t}}}, onset_spread_bp, onsets_by_context: {burst |
flush: {after_rise | after_fall | flat | unknown: ...}}, separation_bp,
by_label, by_bucket}`. `POST /api/eyes/backtests` adds `variants: [{name?,
base?, values}]` (at most `EYES_BACKTEST_MAX_VARIANTS`): templates made for the
run only (`var-NN`), never stored; a variant's manifest entry adds `variant:
true`, `base`, `overrides`, and every template's summary adds `exits`, `flush`
and `vs_base: {base, paired, avg_r_delta, better, worse, same} | null` -- the
same setups (day, symbol, leg) against the run's first template.
`tools/eyes_backtest.py sweep` builds the variants from a grid.

## Signal trials (ADR 041, operator decision 2026-09-30)

"how can we use all this data to determine if we should buy or sell or hold?" -- a study of every
Level 2, Time & Sales and setup signal on 6 recorded days found no buy edge, and a 30 s flush exit
and two don't-buy states that held in sample only (`F:\Nova\eyes\studies\buy-sell-hold-2026-09-29\`).
A tape or book reading becomes a call (or an automated action on a practice venue) only by passing a
trial registered before its data exists. The registry is `knowledge/signal-trials.json`:
`{schema_version: 1, registry: "signal-trials", adr, registered_at, data_from, frozen: true, note,
reading: {when, multiplicity, peeking, failed}, common: {recordings, prints, random_long: {every_sec,
entry, filters: {ask_min, ask_max, max_spread, quote_max_age_sec}, bracket: {target_cents,
stop_cents, time_stop_min}, fills}, lag_honest_exit, control, costs}, trials: [{id, name, role:
"sell" | "sell_bot_only" | "buy_veto" | "buy_warning", signal, rule, population, primary_metric,
test, sample: object, pass: string[], reported_not_deciding: string[], on_pass, on_fail, in_sample:
{study, evidence}}]}` -- T1 the 30 s flush exit on random longs, T2 sellers own the last 10 s, T3 a
red burst at bot speed, T4 a down-sweep, T5 a planned risk under 5c, T6 the 30 s flush on setup
trades. Only data dated `data_from` (2026-09-30) or later counts; each trial is read once, when its
sample is complete, Holm-adjusted across the trials read that night, and shows n of N until then.
The file is frozen: `backend/tests/test_signal_trials_registry.py` holds its canonical JSON (sorted
keys, no whitespace) to the SHA-256 it was registered with, so a change is a new trial on new days,
never an edit. Trials registered after it go in a new registry version, `knowledge/signal-trials-2.json`
(the same shape plus `version: 2` and `follows`; its own hash in `test_signal_trials_registry_2.py`): T7
Room under 2R to the first level of today's map, as a warning, on setups armed from 2026-10-01 ("The day's
levels" below). Then `knowledge/signal-trials-3.json` (`version: 3`, follows the second; its hash in
`test_signal_trials_registry_3.py`): T8 the 5-minute chart against a 1-minute setup at its trigger, as a
warning, on triggers recorded from 2026-10-01 ("The 5-minute chart on a 1-minute setup" above). No trial lets
Nova buy or sell on Live by itself. Recorded with it (built later):
a planned risk under 5c warns and never blocks until T5 passes; a "Flush exit 30 s" template plays
on Nova's Paper bot (put in play outside the bot's window, out again if T1 fails); Approve may hold
Nova's flush and 15-minute exits on Paper and on Sim at the live edge; the Trader's WAIT and SELL
NOW · FLUSH lines show as calls marked "in trial" (description only on Live) until read.

## Setup templates, the eyes' journal and replayed eyes (ADR 029, operator ask 2026-09-23)

`GET /api/setups/templates` (owner `backend/setup_templates/`) answers
`{schema_version: 1, error: string | null, max_per_setup, setups: [{id,
scanner: boolean, catalogue: {setup, scanner, source, groups: [{id, label,
blurb, params: [{key, group, label, kind: "number" | "int" | "bool" | "time" |
"choice", default, unit, min, max, step, choices: [{value, label}], nullable,
help, live}]}]}, in_play, templates: [{id, setup, name, note, rev, values:
{KEY: value}, builtin, in_play, fingerprint, error: string | null, created_at,
updated_at, readout?: {state, passed, reason, go_triggered, min_go,
go_avg_net_r}}]}]}` -- values in the unit the operator types (percent as 5, a
float in millions of shares); a nullable parameter is off when `null`;
`readout` only on a setup with a scanner. Writes need the desk's API key even
on loopback, like bot routes (a template sets the bot's entry rules):
`POST /api/setups/templates/{setup}` `{name, from?, values?, note?}` -> 201;
`PATCH .../{id}` `{name?, values?, note?}` -> `{template, rules_changed,
setup}` (a change to `values` bumps `rev`; a rename does not); `DELETE
.../{id}`; `POST .../{id}/play`. Every write answers `setup`, that setup's
view. A refusal is `{detail: {reason, error, field}}`: `TEMPLATE_INVALID` 400,
`SETUP_UNKNOWN` / `TEMPLATE_UNKNOWN` 404, `TEMPLATE_BUILTIN` /
`TEMPLATE_LIMIT` / `TEMPLATE_NAME_TAKEN` / `TEMPLATES_UNREADABLE` /
`TEMPLATE_NO_PARAMS` 409. The built-in `default` (the pre-registered rules at
`SETUP_TEMPLATE_DEFAULT_REV`) is never stored and never edited. The store is
`setup-templates.json` in the operator cache: `{schema_version: 1, setups:
{SETUP: {in_play, templates: [{id, name, note, rev, values, created_at,
updated_at}]}}}`; an unknown version or an unreadable file leaves every setup
on its default and refuses writes.

The setup scanner runs one lane per template of every setup with a scanner
(ADR 031): every template is watched; each setup's template in play proposes
(at Eyes or above) and draws that setup's rows. `setups.db` was `PRAGMA
user_version = 2` here -- rows add `template_id`, `template_rev` (integer) and
`params_hash`; a version-1 file migrates in place and its rows become the
default's (ids stay `SYMBOL-DATE-LEG_T`; another template's rows end
`~TEMPLATE_ID`) -- and is 3 since ADR 031 (`setup_type`, `detail`). The board payload adds `source: "live" | "sim"`, `template:
{id, rev, name, params_hash} | null`, `templates_watched` and `replay: {kind:
"capture" | "journal", date, symbol, playhead, at, loading, error, note,
recording, loaded?, gap?, journal?} | null` (`journal`: "Recorded eyes in Sim"
below; its `setups[]` add `recorded: boolean`); a row's `state` may be `filtered` (the template's stock
filter kept the name out, and the reason says which rule); a proposal adds
`template_id`, `template_name` and `source`. The read-out's `rules` adds
`template: {id, rev, name}` and counts only that template revision's rows.
`bot/entry_rules` reads each setup's bot window from its template in play
(`bot_window_start` / `bot_window_end`); the daily cap is the venue sleeve's
`entries_per_day` (ADR 042), and `bot_entries_per_day` left the catalogue: a
stored template that carries it loads without it (listed on the wire as
`retired: [{key, value, text}]`), and a write that sends it is refused
`TEMPLATE_INVALID`. **The bot's rules never restart a read-out** (ADR 042):
the parameters in the `bot` group are left out of a template's `rev`, its
fingerprint and `params_hash` (every catalogue param carries `affects_readout:
boolean`; a save touching only bot parameters answers `rules_changed: false`
and keeps the revision). **The bot window sits inside the arming window**: a
write whose bot window reaches outside the setup's arming window is refused
`TEMPLATE_INVALID` naming the field and both windows; a stored window outside it
is clipped when read, and a window wholly outside is empty (the bot never
enters on that template). A template adds `bot_window: {start, end, clipped,
empty, arming: {start, end}, stored: {start, end} | null, note} | null`; red to
green's built-in is 09:30-10:00. The read-out adds `bot_window: {start, end,
clipped, triggered, triggered_inside, go_triggered, go_triggered_inside} |
null` (its pre-registered rules unchanged). A setup without a scanner takes no
template writes: create, update and play are refused 409 `TEMPLATE_NO_SCANNER`. `GET /api/setups/scoreboard` and
`GET /api/setups/rows` answer for the template in play (its id and current
revision) unless `template=` names another template id (every revision) or
`all` (every template: a variation re-scores the same legs, so counts
overlap); both add `template: {id, rev, name} | null`.

**The eyes' journal** (`backend/eyes/journal.py`):
`<eyes dir>/journal/YYYY-MM-DD.jsonl` (`NOVA_EYES_DIR`, else `F:\Nova\eyes`
when F: is mounted, else `<cache>/eyes`; the file is the wall clock's Eastern
date), one line per observation: `{schema_version: 1, wall_ts, ts, date,
source: "live" | "sim" | "backtest", event, symbol, template, rev, playing,
bot: {level, active, venue} | null, replay?: {date, symbol}, ...}`, where
`event` is `session | lanes | watch | beat | leg | state | armed | filtered |
rearmed | near | tape | price | triggered | failed | disarmed | proposal |
scored` and carries its own fields (`setup` levels, `grade`, `pillars`,
`reason`, `tape` / `verdict` / `reasons` / `metrics` / `line`, `status`,
`outcome`, `bar_r`, `mfe`, `mae`, `added` / `removed`, `lanes`, `count`). `ts`
/ `date` are the moment and session the eyes looked at (a replay's own). A line
from a lane adds `setup_type` (ADR 031). Since 2026-09-24 every line about a
symbol carries the detector's `last` price and `leg` (`null` when none), a
`triggered` line its `reason`, a `state` line `kind` and `nth`; the lane writes
a `state` line whenever the detector's state or reason differs from what its
last line implied (`setup_scanner/lane_view.JOURNAL_EVENT_STATES`; writer
`setup_scanner/lane_journal.py`), the playing
lane a `price` line for a name armed or near at most every
`EYES_JOURNAL_PRICE_EVERY_SEC` (5 s), and the live engine a `beat` line (`count`:
names followed) every `EYES_JOURNAL_BEAT_SEC` (60 s). `NOVA_EYES_JOURNAL=0` turns
it off. Read by `tools/eyes_journal.py` (`days | summary | setups | events |
board`) and `eyes/reader.py`; the desk reads one symbol's day through `GET
/api/stock-read/{symbol}/decisions` (ADR 036), and the Sim desk off the live
edge every card at the playhead ("Recorded eyes in Sim" below).

**Replayed eyes** (`backend/eyes/replay.py`, `sim_eyes.py`, `backtest.py`): a
Session Record's prints (per second, the high then the last of the prints that
set a price), its recorded books (sampled every 0.5 s) and the day's archive
minute bars (else the recording's `bars_1m`) through the same lanes; outside a
recorded stretch nothing is near and nothing triggers. `GET /api/eyes/journal`
-> `{writer: {enabled, dir, written, dropped, queued, last_error,
last_write_ts}, days: [{date, bytes, path}]}`; `GET /api/eyes/sim` -> `{target,
loading, error, template, lanes, recording, now}`; `GET /api/eyes/backtests`
-> `{dir, runs: [{run_id, created_at, finished_at, status, error, templates,
sessions, setups}]}`; `POST /api/eyes/backtests` `{setup?: SETUP, templates?: [id],
sessions?: [{date, symbol}]}` -> 202 `{run_id, status: "running"}` (400
`BACKTEST_INVALID`, 404 `TEMPLATE_UNKNOWN`; `setup` defaults to
`first_pullback`, and `templates` are that setup's; ADR 031); `GET /api/eyes/backtests/{run_id}`
-> `{manifest, summary}`. A run is `<eyes dir>/backtests/<run_id>/`:
`manifest.json`, `setups.jsonl`, `events.jsonl` and `summary.json`, shaped in
`eyes/backtest.py`'s docstring; never `setups.db`, never the live read-out.

**Recorded eyes in Sim** (`backend/eyes/playback.py`, operator ask 2026-09-24:
"i want this stuff to be recorded when they show up ... viewable in the sim ...
when something pops up ... so we can fine tune them when things dont match").
On the Sim desk off the live edge without a Session Record loaded -- nothing
loaded, a past day, a historical download -- the Setups board and every setup
card on the Bots page are the live eyes' journal of the playhead's Eastern date
folded up to the playhead: `source: "sim"`, `replay.kind: "journal"`, the rows,
each setup's funnel and the proposals open then, in the live board's shape.
Only `source: "live"` lines of that session count; no line after the playhead
is read; nothing is recomputed with today's rules (a loaded Session Record still
re-reads the recording with today's templates, `replay.kind: "capture"`). A
recorded proposal is pushed on `/ws/setups` as an alert when the playhead plays
across its moment (a step of at most `EYES_PLAYBACK_ALERT_STEP_SEC`, 120 s),
never on a jump or a rewind; nothing proposes (`proposing: false`). `replay`
adds `loaded: "historical" | "capture" | null`, `gap: {reason: "no_record" |
"before_record" | "not_running", since, until} | null` and `journal: {path,
exists, lines, folded, first_ts, last_ts, line_ts, skipped}`; `note` states the
absence. A silence longer than `EYES_PLAYBACK_GAP_SEC` (180 s) after a `beat`
of the same session is `not_running` (Nova closed or its eyes off), and a gap
draws no rows, no proposals and zero counts -- never the board carried across
it; a day written before beats existed has no gap check. A `session` line (Nova
started) begins the fold again from nothing, as the live eyes did. Each
`setups[]` summary adds `recorded: false` for a setup whose scanner was not
running at the moment; its level, template and window stay today's controls
(the window of the template that played then). `GET /api/eyes/at?date=YYYY-MM-DD&at=<epoch>`
-> `{schema_version, date, at, gap, note, journal, proposing, setups, rows,
proposals, universe, universe_symbols}` (the names the eyes followed then; 400
`EYES_DATE_INVALID`); `py -3 tools/eyes_journal.py
board --date D --at HH:MM[:SS]` prints the same. A backward scrub refolds the
day at most every `EYES_PLAYBACK_REBUILD_MIN_SEC`; the file is read off the
scanner's loop, as it grows.

**Every locked control says why** (frontend, `ux/whyTip.ts`): a control that
cannot act carries its reason in `data-why` beside `disabled` (or
`aria-disabled="true"`); one tip per window shows it on hover and at once on a
refused press. `ux/whyCoverage.test.ts` fails the build on a JSX element that
can be disabled without its reason.

**Every chip explains itself** (frontend, `ux/hoverTip.ts`, ADR 031): an enabled
element that carries `data-tip` (and optionally `data-tip-title`) shows it in one
tip per window on hover and on keyboard focus -- plain text, line breaks kept,
never HTML. A locked control keeps `data-why` (the two never stack). The setup
cards, the Setups board and the Symbols card explain every state, tape verdict,
grade, price, count, level and read-out this way; `title` stays for short labels.

**Ctrl+F finds on the page** (frontend, `ux/findBar.ts` + `ux/findText.ts`,
operator ask 2026-09-24: "can we also do like CTRL+F so maybe we can search on
anything in that screen instead of looking everywhere?"). Electron has no find
bar, so every window installs one from `main.tsx`: Ctrl+F opens it, typing
marks every shown match (CSS highlights; case ignored, spacing flexible, never
across two blocks, never hidden panels, tooltips or text fields), Enter /
Shift+Enter move, Esc closes and gives focus back. While it is open a changed
page is searched again at most every `FIND_REFRESH_MS`, keeping the current
match, never scrolling on its own. It yields Ctrl+F to a Nova Action bound to
it (the hotkey dispatcher marks the key handled first), and every key typed in
its box stays in the box. It reads only what is drawn as text: a chart's canvas
and a list's undrawn rows are not found. The Ctrl+Alt shortcuts menu lists it.

