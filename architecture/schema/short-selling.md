# Data schema: Short selling

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/short_sale/, backend/short_proof/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Short selling (ADR 048, operator decisions 2026-10-01 to 2026-10-07; #778)

"Short selling: Paper and Sim first, Live last" -- built in six steps under #778 (ADR 048 "The build"),
each safe alone. This section says what is on master (steps 1-6); ADR 048 is the whole design and ADR
049 the five short strategies, pre-registered. Paper and Sim short, by hand from the Trader and by Nova's
bot, Auto-entry and Approve on the short strategies at On ("The bot trades both sides" below); Live still
refuses every short -- `IBKR_SHORT_ENABLED` is the operator's, set last, and the Live short proof refuses
one until it is complete ("Live readiness" below) -- and a bot never trades Live.

- **The one short check** (owner `short_sale/`: the rules `check.py`, pure; the door `door.py`, run by
  `execution.validate.check_account_and_position` under the execution lock for every place or bracket
  carrying `short_entry`, on every venue). In order, the first failure refuses with its rule, its
  numbers and its fix:
  1. Live only: the Live key, `IBKR_SHORT_ENABLED` (`SHORT_DISABLED`, ADR 009), then the Live short proof
     (`SHORT_PROOF_INCOMPLETE`, naming what is missing; "Live readiness" below). Paper and Sim need neither;
  2. a SELL and a limit -- a place's `limit_price` on a `LMT`, a bracket's `entry_price` (`SIDE_INVALID`,
     `SHORT_NEEDS_LIMIT`) -- with a buy stop above it: a short is a bracket, a plain limit carries no stop
     (`SHORT_NEEDS_STOP`, ADR 048 1.6). On Paper and Sim its target may be left out (a two-leg bracket:
     the entry and its stop); a Live bracket still sends both exits;
  3. never while the account holds the stock long (`SHORT_WHILE_LONG`: Nova never flips);
  4. a margin account (`account_class: "margin"`, `SHORT_NOT_MARGIN`) -- on Live by IBKR's own figures
     (`ibkr_account_class`; the `IBKR_ACCOUNT_CLASS` override in `.env` never counts for a short) -- with at
     least $2,000 of equity (`SHORT_EQUITY`); unreadable equity is `SHORT_MARGIN_UNKNOWN`;
  5. the hours by the venue's clock (`short_sale/hours.py`; the playhead on Sim): new shorts from 09:35
     ET until ten minutes before the close, 15:50, or 12:50 on an NYSE early close (`SHORT_HOURS`);
  6. halts (`short_sale/halts.py`): not halted (`SHORT_HALTED`), not within 10 minutes of an up-halt's
     resumption (`SHORT_HALT_COOLOFF`; a halt Nova cannot place is up), never unknown (`SHORT_HALT_UNKNOWN`);
  7. borrow: the cached tick-236 read, fresh and `shortable_est`, covering this order plus the shares
     already short plus the short entries in flight (`SHORT_STALE_BORROW`, `SHORT_NOT_SHORTABLE`,
     `SHORT_BORROW_TOO_SMALL`); a past-day replay reads the borrow recorded then
     (`SHORT_NO_RECORDED_BORROW`);
  8. SSR (`short_sale/ssr.py`): while SSR is on or unknown, the short's limit must be over the bid
     (`SHORT_SSR_AT_BID`; no bid to price over, `SHORT_SSR_NO_BID`);
  9. margin: IBKR's what-if for the stock, else the published rules (`short_sale/margin.py`; constants
     `constants_shorts.py`): a short's maintenance is $2.50 a share under $2.50, 100% of value to $5,
     $5 a share to $16.67 and 30% above, a long's 25% of value. The account's maintenance now is the
     account's own (`NetLiquidation - ExcessLiquidity`: IBKR's on Live, the ledger's on a practice
     venue); shorts in flight elsewhere add theirs at their limits. This stock's shorts in flight keep
     their own limits too (never repriced at the new entry): the whole short is judged at the highest of
     those prices, its fill price, when the last of it is sold. The short already held keeps its mark now
     (its position row's price; unreadable is `SHORT_MARGIN_UNKNOWN`): by the time the price reaches a new
     short's entry over the market, the held short has lost that move. `SHORT_MARGIN` when the requirement does
     not fit there, `SHORT_CUSHION` when IBKR would liquidate within a 25% move over it (the liquidation
     price, where equity meets maintenance with every other position held still, under `fill * 1.25`).
- **Nothing under the lock waits on IBKR** (`short_sale/prelock.py`, `facts.py`). Before the lock the door
  gathers a short's facts -- the cached borrow, the kept what-if, SSR, the halt, the venue's quote and
  clock -- from memory or small local files. A bot's short may wait `SHORT_WHATIF_BOT_WAIT_SEC` (1.5 s)
  for IBKR's what-if; the ticket's short never waits (ADR 045's deadline): the what-if is asked in the
  background and the order is judged by the answer kept for the stock, else the published rules. A Live
  short while the key is off gathers nothing. A missing or stale borrow asks IBKR on a worker thread
  (`request_refresh`) and the short is refused with the fix ("place the short again in a moment"); an open
  Trader tab's ticker socket re-reads borrow every `IBKR_SHORTABILITY_REFRESH_SEC` (20 s), under the 60 s TTL.
- **IBKR's what-if margin** (`ibkr/margin_whatif.py`, `short_sale/whatif.py`; ADR 048 decision 2). One
  `whatIfOrderAsync` with a DAY limit -- never `placeOrder` -- and never for a stock the account holds
  (IBKR would net it). An answer becomes the stock's **ratio** per side: IBKR's maintenance change over the
  published rules' requirement for the same order (over 1 where IBKR charges a volatile name extra), read
  as current for 60 s and kept 8 hours, in memory. Every practice margin figure scales that stock's
  published maintenance by its ratio and names its source ("IBKR what-if" or "published rules"); a
  past-day Sim replay uses the published rules. Before a Paper or Sim buy, the door asks in the background
  for the next order.
- **The practice account's margin** (`practice/margin.py`, `practice/ledger.py`). Buying power is (equity
  - maintenance) x 4 at $2,000 of equity or more, else the cash; a long is held to buying power, a short to
  its maintenance against the equity left over it (none under $2,000). The account summary adds IBKR's own
  `MaintMarginReq` and `ExcessLiquidity`. A practice account starts at $5,000 (`PRACTICE_STARTING_CASH`,
  so $20,000 of buying power), the operator's own account size; a reset with no amount returns to it.
- **Shorts on Paper and Sim** (`practice/broker.py`, `practice/order_rules.py`). A short entry is a SELL
  from flat or adding to a short; while the account holds the stock long it is refused
  `PRACTICE_SHORT_WHILE_LONG`, at placement and again at the fill (a long opened since cancels it). A
  short is never inferred: a SELL past the held quantity without `short_entry` stays `PRACTICE_NO_SHORTS`,
  and so does a bracket whose entry is a SELL without it, at the broker as at the door (`short_entry` on a
  BUY is `SIDE_INVALID`). A short bracket's exits are BUYs that close what the entry opens; with no target
  it is two orders. A working short entry is never repriced in place: a replace runs no short check, so the
  door refuses it `SHORT_REPRICE` ("cancel it and place it again"); its exits still move. On Live too (step
  6): the door finds Nova's own Live short entries in the execution record (`execution/store_orders.py`), and
  a record it cannot read refuses the replace. **SSR at the fill** (`short_sale/ssr_fill.py`): while SSR is on or unknown, a short
  entry fills only at a price over the venue's bid at that moment -- at placement the bid now; on a print
  the bid that stood when it traded (the reference's `bid_at`: a Massive window's NBBO before it, a
  recording's quote then, the top of book a live print met at receipt, kept in `tape_trades`), never the
  bid at the playhead or the matcher's pass. Otherwise it keeps resting (never cancelled for SSR), and a bid
  Nova cannot see proves nothing. A cover is never held by SSR.
- **SSR** (Reg SHO Rule 201): on once a trade reaches 90% of the prior close, for the rest of that day and
  all of the next; `on`, `off` or `unknown`, and unknown counts as on. Today: the prior close is IBKR's tick
  9, else its regular-hours daily close, else the leaderboard's; a trade reached the trigger when IBKR's day low (tick 7), the last
  trade, a stored 1-minute low or the whole-day bar did; off only when the whole day's low is known (IBKR's
  04:00-20:00 daily bar read at or after 09:30, and the day low since). Yesterday: on when its low reached
  90% of the session before's regular-hours close. IBKR's two daily reads (`historical_service.
  request_daily_bars`, `useRTH` both ways) are asked once a stock a day on a worker thread. A past-day
  replay is on when its own prints reached the trigger, else unknown -- never off.
- **Halts.** Live: `ibkr.halt_status.halted_now` (IBKR's tick 49, then the Nasdaq halt list), with the
  resumption each remembers (`halt_status.last_resume`, `clear_since`; `nasdaq_halt_feed.last_resume`). A
  halt's side is LULD's band when LULD held it (`luld.live.halt_side`), else the price's direction over the
  5 minutes before it. A past-day replay reads that day's halt log (the leaderboard's `halt_events`) at
  the playhead.
- **Borrow, recorded** (`short_sale/borrow_log.py`). Every tick-236 read Nova makes is kept for good in
  `<root>/borrow.sqlite3` -- `NOVA_BORROW_DIR`, else `F:\Nova\borrow` while F: is mounted, else
  `<cache>/borrow` -- `PRAGMA user_version = 1` (an unknown version refuses), one table `reads (symbol, ts,
  shares, state, source)`; nothing prunes it. Writes are enqueued and one thread writes them;
  `NOVA_BORROW_LOG=0` turns it off. A past-day Sim replay shorts only on the newest read at or before its
  playhead, and one older than the 60 s TTL there is no read.
- **The day cover and the margin call** (`short_sale/closes.py`, every second from `short_sale/runner.py`;
  `NOVA_SHORT_RUNNER=0` off), on each practice venue this process has loaded, by its own clock:
  - while the clock stands outside the short hours (09:35-15:50, 12:50 on an early close), Nova cancels
    every working short entry on the venue, its waiting exits with it: one the door let go before 15:50,
    or a GTC one into the next morning, would otherwise open a short the hours forbid. A short entry also
    lapses at any hour once its own day is over (`short_sale.hours.entry_lapsed`): one Nova was closed over
    is cancelled when it comes back after the next 09:35 too, since its borrow, SSR, halt and margin checks
    were the day before's. Its day is when it was first placed (practice rows add `entered_ts`, the venue's
    clock then; a replace re-dates `placed_ts`, never `entered_ts`). A fill that would land outside its day's
    hours is refused at the fill too (`SHORT_HOURS`, `practice.order_rules.fill_refusal`), so a Sim jump past
    15:50, or the next day's prints, never fill a short before this pass runs;
  - at 15:55 ET (12:55 on an early close), and whenever the clock stands outside the day's hours, Nova
    cancels a short's working orders and covers it at market;
  - when the account's equity falls under its maintenance, Nova closes the position that needs the most
    -- shorts first -- at market, one a pass.

  Each close is an ordinary order through the execution door: source `flatten` (protective), origin
  `day_cover` / `margin_call` (`EXECUTION_ORIGINS`), sent to the venue that holds the position whatever
  the desk shows: `ExecutionCommand.target_venue` now admits the kill switch's cancels and these closes'
  `cancel_working` cancels and `flatten` places -- to Paper or Sim, and to Live for the day cover alone
  ("Live readiness" below) -- and nothing else (`execution/venue_door.py`). Each writes a `day_cover` /
  `margin_call` line on the bot audit stream; a close the venue refuses is tried again
  `SHORT_CLOSE_RETRY_SEC` (15 s) later, not on every pass, and a day cover that cannot go out raises the
  alarm every desk window shows ("Live readiness" below).
- **Shorts in flight.** A short entry, a place or a bracket, is committed in `execution.inflight` as side
  `SHORT` with its limit (never as `SELL`: it spends no long, so a closing sell keeps its shares) until its
  order resolves; the borrow and margin checks count it.
- **A cover is a close.** A BUY place while the account is short the stock (`execution.position_checks.covers_short`)
  is held to the short less the covers in flight (`OVERCOVER`) and never to buying power, and the all-stop's
  day lock never refuses it (`bot.buy_lock.buy_refusal(..., covers=True)`). A position Nova cannot read is no
  cover: the BUY then meets buying power and the position check, as before.
- **What an order does** (`execution/order_side.py`; the Side column). Every order row, working and closed,
  on every venue, carries `position_side: "long" | "short" | null` and `effect: "opens" | "closes" | null`,
  beside `short_entry: boolean | null` (Nova's record that the row is the SELL it sent as a short entry). A
  practice row stamps them when placed (`practice.order_rules.side_fields`; a bracket's exits close what
  their entry opens). A Live row Nova sent reads its execution row: `short_entry`, a bracket's legs, and the
  new payload field `position_at_send` (the signed position the door saw as it sent; `null` when it could
  not read it) (`execution/sent_by.py`). A Live working order placed outside Nova reads the position now; a
  closed one Nova has no record of reads `null`. **Fill now** refuses a row with `short_entry: true` before
  it cancels anything: it would re-send the short without its buy stop.
- **Positions say their side and where IBKR would liquidate them** (`short_sale/positions.py`).
  `GET /api/ibkr/positions` rows add `position_side`, `liquidation_price: number | null` and
  `liquidation_source: string | null`: the price where the account's equity -- this position marked
  there, every other position held still -- meets the maintenance requirement (Paper and Sim: the ledger's,
  by the what-if ratio; Live: IBKR's equity and maintenance). `null` when the account cannot be read or the
  position can never be liquidated by its own price alone (a long the account pays for in full).
- **The check, read-only** (`short_sale/routes.py`). `GET /api/short-check/{symbol}?qty=&price=&stop=&target=`
  answers `{schema_version: 1, symbol, venue, generated_at, now, replay, ok, first: {text, code} | null,
  rules: [{id, label, ok, state: "ok" | "bad" | "unknown" | "info", text, code, value, numbers}], facts:
  {bid, ask, last, borrow: {shares, state, age_sec, stale, source: "live" | "recorded"} | null, whatif:
  {...} | null, whatif_error, ssr: {state, effective_on, text, since, trigger, prior_close, low}, halt:
  {state, text, resumed_at, until, side, source}, hours: {date, half_day, open, last_short, cover, close} |
  null}}` -- the verdict the door would give, for the desk venue. Asking places nothing; it may wait up to
  `SHORT_WHATIF_TIMEOUT_SEC` (2 s) for IBKR's what-if, as no order waits on it.
- **Never past flat at the fill.** The practice broker cancels a cover that would buy past the short when its
  print arrives (`PRACTICE_OVERCOVER`: "A cover never buys past flat: Nova never turns a short into a long"),
  as it cancels a SELL past the long (`PRACTICE_NO_SHORTS`, QA R42).
- **Freeze all orders keeps protective stops** (`kill_switch/sweep.py`). Working stops (`STP`, `STP LMT`,
  `TRAIL`) on the side that closes a position the venue holds -- SELL stops under a long, BUY stops over a
  short -- stay resting, together never larger than that position: two that each cover it would both fill
  and flip it. They are kept in turn until the next would pass the position -- first a stop Nova cannot
  cancel (it rests anyway), then the nearest the market, then the oldest -- and the rest are cancelled and
  named in the venue's `note`. A bracket exit whose entry is still working with nothing filled protects
  nothing and is cancelled with it; Live order rows carry IBKR's `parentId` as `parent_id` for this, so the
  ticket's Flatten counts a Live bracket's exits once too. Each venue's sweep adds `kept: [{order_id, symbol,
  side, qty, order_type, stop_price, why}]` and the trip's answer `kept_order_ids`; positions Nova cannot
  read keep no stop, and the venue's `note` says so. The header's red KILL, which flattens, still cancels
  everything first.
- **On the desk.** The Orders tables add a **Side** column (LONG / SHORT, Buy / Sell, opens / closes; "?"
  when not known, with why), the Positions table **Side** and **Liq. price**; Sent by names "Day cover" and
  "Margin call"; a short's Flatten reads "Cover 416 (flatten)". A short is orange and always carries the word
  SHORT (`--short*` tokens): VWAP and the Paper chip are orange too, so the colour alone never says it.
- **The ticket follows your position** (step 3; `ibkr/shortTicketModel.ts`, `useShortTicket.ts`,
  `useTicketSideActions.ts`). Flat: Buy / Short. Long: Buy / Sell, Short off ("Nova never flips"). Short: Cover /
  Short more, Sell off. A side that cannot be pressed says why.
  - A short is a Limit with a **required Buy stop**, started at the venue's offset over the limit (Settings >
    Trade, per venue, `shortStopOffset`, default $0.10). Under SSR, on or unknown, the Limit starts at the ask.
  - A **SHORT CHECK** box under the ticket lists the one short check's rules with their numbers
    (`GET /api/short-check`, asked while Short is chosen). It describes; the door decides.
  - The submit reads "Short RDYN · 416 @ 5.77 · stop 5.89" in orange; while short, "Cover RDYN · 416 @ 5.46"
    in green. The cost line reads the short's value and its margin.
  - `POST /api/ibkr/order` takes a short's `stop_loss_price` alone (`short_entry: true`, no
    `take_profit_price`): a two-leg bracket, which the door takes on Paper and Sim. With Settings > Trade's
    default take-profit on, the cover target goes too. On Live the ticket's Short stays locked while
    `IBKR_SHORT_ENABLED` is off, and once it is on, while the Live short proof is incomplete or cannot be
    read (`/api/ibkr/status` `short_proof`); on Live the Short side shows only for a margin account by IBKR's
    own figures (`ibkr_account_class`).
- **Hotkeys** (`hotkeys/runNovaActionShort.ts`): `short_limit_bid_offset` / `short_limit_ask_offset` (a Short with
  its own buy stop: the hotkey's `stopOffsetDollars`, else the venue's offset; "SS1 Bid+1"),
  `cover_limit_ask_offset` (the whole short at the ask plus an offset) and `cover_pos` ("Cover all": the whole
  short at market). Both covers are protective like Flatten (`intent: "flatten"`): never past flat, never on a long,
  and refused while the short's own buy stop rests ("cancel that order first, or use KILL"). DAS `SHORT` commands
  import as a Short at Bid / Ask plus an offset.
- **Chart and Level 2.** The chart menu adds "Short @ price" (staged on the ticket's Short side; on a long its
  own reason under the row). Level 2 adds chips beside the borrow chip, from the short check for one share:
  SSR off / on with its trigger / "SSR ?", COOL-OFF while an up-halt's 10 minutes run, and LIQ (the position's
  liquidation price). A short plan marks SHORT and STOP ↑ with the asks and TARGET ↓ with the bids; a held
  short STOP ↑ and NEXT ↓.
- **A short plan** (the stock read, ADR 036). `GET /api/stock-read/{symbol}` takes `side=short` for your own
  plan (a hand short: your buy stop over the entry, else the highest high of the last 3 closed 1-minute
  candles; the cover at entry - 2R), and every plan adds `side: "long" | "short"`. Its checks, levels, room and
  round numbers are measured downward, and "Too thin to trade" walks the bids. The plan box carries a SHORT
  tag, reads Short at / Buy stop / Cover, lists the short check's rules in its check list, and "Stage short
  in ticket" fills the ticket's Short side with the plan's buy stop. "Short at the bid" starts a hand short.
  Approve on a short setup sends it with its buy stop and cover ("The bot trades both sides" below).
- **Holding a short.** The read takes `held_side=short` (with `held_qty`, a positive count) and answers
  `held` with `side: "short"`, `lower: {to, round, at, text} | null` (`raise` null) and ladder roles adding
  `resistance` (`stock_read/held_short.py`). The "This trade" card is the mirror: Shorted at, Buy stop, Next
  (under the price), At the stop and Cover 2R; a round a 1-minute candle closed under offers "Lower stop to
  X"; Stage cover fills a buy limit at the ask. The card's stop is the one you set for the tab, else the stop
  order resting at the broker (`stock_read/protectiveStop.ts`: a short's lowest working BUY stop, a long's
  highest SELL stop; "is working at the broker"), else the one proposed. **Nova takes the cover** is `POST
  /api/stock-mode/{symbol}/take-exit` on a held short: a BUY stop over the price for every share short,
  lowered -- never raised -- at each round a candle closes under (`held_short.lower_for`), Paper and Sim only;
  the trade carries `side: "short"` and the audit says `lowered`. The badge reads "SHORT 416 · BROKE $5.50 ·
  NEXT 5.35" or "STOP ↑ 5.89 HIT · COVER" with COVER NOW, and the track Forming · Trigger · Short · Your cover.
  No flush call on a short: trial T1 reads a long's tape.
- **Who trades: Entry · Exit.** `GET /api/stock-mode/{symbol}` adds `entry` / `exit` and `locks.entry` /
  `locks.exit` (`buy` / `sell` stay, the same values, one release), and a trade adds `side`; `PUT` takes
  `{entry, exit}` (or `{buy, sell}`). On the desk the switches read Entry and Exit, each You | Bot; the modes
  "you enter · you exit", "you approve · bot exits", "bot enters · you exit", "bot enters · bot exits"; the
  answers "Bot may trade RDYN: no · Entry is You", with Entry on Bot "Long or short: the strategy decides ·
  forming now: ...", and while you hold it short "You hold RDYN short: the bot enters nothing on RDYN while
  you do". Nova never enters against a position you hold: the bot, Auto-entry and Approve skip a long entry
  while the venue holds the stock short, and any entry while the position cannot be read
  (`BOT_SKIP_HELD_OTHER_SIDE`; the view's note `held_other_side`).
- **Close of day.** The 15:50 card for a Paper short names Nova's 15:55 day cover, and so does the card for a
  Live short while `IBKR_SHORT_ENABLED` is on (`/api/ibkr/status` `short_enabled`); with it off a Live short
  reads "be flat by 15:55".

## The short setups on the scanner (ADR 049, step 4 of #778)

Five short setups run on the setup scanner's lanes beside the long ones (owners `setup_scanner/` and
`setup_templates/`; the rules are ADR 049, pre-registered, with its step 4 section). Read-only like every lane:
nothing here places, stages or cancels an order; Nova's bot trades them at On ("The bot trades both sides" below).

- **The setups.** `setup_type` adds `backside_lower_high`, `bear_flag`, `failed_breakout`, `lost_vwap` and
  `ssr_bounce`, after Gap and Go. `kind` adds each id and `second_<id>`; Lost VWAP has only its own. Each starts at
  Off on every venue.
- **Their windows** are their bot windows: backside lower high and failed breakout 09:35-11:30, bear flag
  09:35-15:30, lost VWAP 09:35-12:00 and the SSR bounce 09:35-15:50.
- **A short reads downward.**
  - The trigger is a low, and the entry is one cent under it. A live price at or under the entry triggers it,
    entering at the minute's open when it gapped under.
  - The stop is over the entry. Target 1 is entry - target R x risk, and the near band is over the trigger.
  - The SSR bounce's entry rests one cent under its level. A live price over the entry fills it at the entry.
- **On the wire.** Every board row, `GET /api/setups/symbol/{symbol}` lane, proposal, trigger event and stored
  row adds:
  - `side: "long" | "short"`;
  - `ssr: "on" | "off" | "unknown" | null`: the short's SSR at its trigger (counting the trade that triggered it),
    else at its arm; null on a long.

  The board's and `GET /api/setups/templates`'s `setups[]` add `side` and `test` (null on a long setup).
- **A short row's grade** (A all five pillars, B four, C three or fewer; unknown is never a pass).
  - `pillars.checks` is `{run, fade, vwap, bad_news, borrow}`.
  - The pillars add `run_pct` (the high of day over the prior close, percent), `fade_pct` (the price at arm under
    the high of day, percent), `hod`, `vwap`, `prior_close`, `bad_news: {dilution, negative, text} | null` and
    `borrow: {shares, state, age_sec, order_shares} | null`.
  - The template's thresholds are `pillar_min_run_pct` (30), `pillar_min_fade_pct` (8) and
    `pillar_borrow_mult` (10).
- **The tape gate and the flow, mirrored** (`tape_gate.evaluate(side="short")`).
  - The level is the bids from the trigger + 1c down to the trigger - `band`.
  - GO is `min_ask_prints` or more prints at the bid, with more shares at the bid than at the ask.
  - WAIT is a buyer of `wall` shares at the level not thinning, a green burst (`red_mult` x the bid volume at the
    ask), or no red yet.
  - VETO is the spread, a buyer of `big_seller` shares at the level, or a hidden buyer (`hidden_mult` x the inside
    bid sold into a bid that did not move).
  - The template keys are the long's; only their words mirror.
  - The flow's entry needs a score at or under minus `flow_entry_min`. A `burst` is a short's flush: tighten the
    buy stop down to `flush_trail_r` R over the price, or cover at the ask.
- **Scoring, mirrored.** R is (entry - exit) / risk; the first touch is target 1 at or under, or the stop at or
  over. The bar exit takes half at target 1 and moves the stop to the entry. Then a close over the 9 EMA covers,
  as does the bailout after `bailout_bars` candles without a close under the entry.
- **The 5-minute read.** `tf5` is null on a short row.
- **SSR.** A breakdown template adds `ssr: "trade" | "skip"`: `skip` filters a setup armed while SSR is on or
  unknown. The SSR bounce arms only while SSR is known on.
- **`setups.db` is schema 6.** Rows add `side` and `ssr`. A schema-5 file migrates in place, its rows `long`.
- **The read-out** of a breakdown setup judges the rows whose `ssr` at the trigger was `off`. It adds `ssr:
  {triggered, scored, win_pct, avg_net_r} | null`, the SSR rows apart, and `rules.ssr_apart: boolean`.
- **The five-year test and the On lock** (ADR 049 §12).
  - A short setup's `test` is `{state: "queued" | "running" | "passed" | "failed" | "error", text, rules_hash:
    string | null, matches: boolean | null, started_at, updated_at, finished_at, summary: {trades, pf, pf_2x,
    exp_r, p} | null, file}`. `matches` says whether the tested rules are the template in play's (`params_hash`).
  - `PATCH /api/bot/session {setup_levels}` refuses On (2) for a short setup, 409 `BOT_SHORT_TEST`, unless its test
    passed on the rules in play. A short setup at On whose test stops matching reads as Eyes.
  - `GET /api/bot/session`'s `setups[]` add `side`, `test` and `locked: string | null` (why On is locked).
  - The harness reads bars, never the tape: a template whose `flush_exit` is not `off` is refused, and its result
    reads `error` (PR #789 review), so a flush exit is never unlocked untested.
  - The operator runs the test on the desk (`research/shorts/README.md`: `select_shorts.py`, then
    `research/orb/extract_minutes.py --selection shorts_selection --table minutes_shorts --start 04:00`, then
    `test_shorts.py --setup <setup>`); a queued card names its own command.
  - The harness writes the result file `<NOVA_MARKET_DATA_DIR>/research/short_tests/<setup>.json`
    (`NOVA_SHORT_TESTS_DIR` moves the folder) through a temporary file and a rename. No agent writes it. Its
    shape:

    ```
    {schema_version: 1, setup, state: "running" | "passed" | "failed" | "error", started_at,
     updated_at, finished_at, harness: {version, command},
     rules: {template_id, template_rev, rules_hash},
     data: {first_day, last_day, days, symbol_days}, assumptions: string[],
     progress: {done, total, unit: "days" | "shuffles"} | null, main, ssr_days,
     criteria: {trades, best_year_removed, costs_2x, neighbourhood, permutation} | null,
     passed: boolean | null, error: string | null}
    ```

    An unreadable file or an unknown version reads `error`.
- **Past setups** (`GET /api/stock-read/{symbol}/past-setups`). A short episode's `after` is read on the mirror:
  `level` is the low it was building over, `floor` the high it would have stopped over, `first` is `low` when it
  broke down under the level first (`high` over the floor), and `trade` is the short the rule refused (entry under
  the level, its stop the floor, its target under the entry). The SSR bounce's `after` is null: its entry rests
  over the price.
- **The journal and auto-record.** A short's `armed` and `triggered` journal lines carry its `ssr`. Auto-record gives
  a short setup a line only while its strategy is On (effective Strategy), and its setups window (`/api/ibkr/status`
  `auto_record.windows`) counts only those: the lines serve ADR 041's long trials, and a short the bot may trade
  needs its tape.
- **On the desk.** Short setups are drawn in orange with ▼ SHORT, live and past. Their cards carry the ▼ SHORT tag,
  the mirrored tape gate words and "Test: five-year test queued / running / passed / failed". Their On is locked
  with the reason until the test passes. A short plan's badge reads "BEAR FLAG ▼ SHORT · ARMED", and its calls say
  SHORT NOW under the trigger; a short proposal stages a short with its buy stop, never a buy.

## The bot trades both sides (ADR 049, step 5 of #778)

One bot, one Bot switch, one list of strategies (ADR 044): **the strategy that triggers decides the side** -- a
long strategy buys, a short strategy shorts. Paper and Sim only, as ADR 042 says: a bot never trades Live. Owners
`bot/first_pullback/` (`short_side.py` the short's own rules), `stock_mode/`, `bot/trigger_short.py`,
`bot/shorts_view.py`; on the desk `frontend/src/bot/` and `frontend/src/stock_read/`.

- **One trade per stock, never a flip.** The first go trigger wins, long or short. The bot, Auto-entry and Approve
  never enter against a position the venue holds (`admit.against_held`, `BOT_SKIP_HELD_OTHER_SIDE`): after a trade
  is flat, the other side needs its own trigger. The bot holds one trade at a time overall. The daily cap
  ("Nova trades a day", the sleeve's `entries_per_day`) counts both sides (`BOT_ENTRY_KINDS`).
- **One sleeve, one bot trip, one all-stop.** A short is sized by the same caps (`bot.sizing.size(..., side)`): its
  risk a share is the buy stop minus the entry. `bot_qty` is signed: a short holds a negative count.
- **A short trigger's own rules** (`short_side.py`), before anything is sent:
  - **The price.** Off SSR the short sells at the scanner's entry. Under SSR, on or not known, it sells at the
    higher of the entry and the ask: above the bid, never under the plan. No ask, an ask not above the bid, or an
    ask at or over the buy stop is a skip, `BOT_SKIP_SHORT_PRICE`.
  - **The check.** The one short check (`short_sale.check.rules`) at that price and size, on the door's own facts
    (`short_sale.facts.gather`, memory reads). Each failure is a stated skip with its code (`SHORT_*`); a check that
    cannot be read is `SHORT_CHECK_UNREAD`. `not_long` is `against_held`'s, and `live_key` never applies.
- **The bot's short** is a practice bracket like its long: a SELL limit with `short_entry`, a BUY limit at target 1
  and a BUY stop. Its audit action is `short_setup_limit` (inputs add `side`, `ssr`, `priced_at_ask`, `short_limit`,
  `short_check`, `short_error`); its trade adds `side: "short"`, `entry_scanned` (the scanner's entry beside the
  priced `entry_planned`), `priced_at_ask` and `ssr`, and R is (fill - exit) / risk. The time stop, the flush exit
  (a `burst`: the buy stop moves down to `flush_trail_r` R over the price, or it covers) and the last-resort close
  cover with a BUY limit at the ask + 3c, then the protective flatten.
- **Auto-entry's short** follows the bot's rules: a two-leg bracket, the SELL limit with `short_entry` and its BUY
  stop, no target -- every cover is yours; its buy stop is cancelled once the position is gone, and the trade stays
  open until it is (a refused cancel is asked again every 2 s and said on the stock). **Approve's short**:
  `POST /api/stock-mode/{symbol}/approve` takes a short plan whose buy stop is over the entry and cover under it
  (`STOCK_MODE_INVALID` otherwise) and sends a short bracket at the trigger, priced as the bot's. Approvals and trades
  add `side`. `BOT_SKIP_SHORT_LATER`, 409 `STOCK_MODE_SHORT_LATER` and the `short_later` note are retired.
- **The localhost bot API** (ADR 016) adds `short_limit_bid_offset` (a short at the bid + 1c as a bracket with its
  buy stop 10c over; no free-form size or stop; refused while you hold the stock long, 409 `BOT_SKIP_HELD_OTHER_SIDE`),
  `cover_limit_ask_offset` (a BUY limit at the ask + 5c), `cover_market` and `cover_pos` (protective: the whole short
  at market, never past flat). Live refuses every one (`BOT_LIVE_NOT_BUILT`).
- **The squares** (`GET /api/bot/triggers`, "One Bots page" above). `gates` add `not_against` ("Not against you")
  after `trades_today`, and `nova_buys` reads "Entry: Bot". The answer adds `short_gates`: `short_borrow`,
  `short_ssr`, `short_halt`, `short_margin`, `short_hours` -- borrow, SSR, no halt in 10 min, margin 25%, before
  15:50. A short trigger's are read from what the bot or Auto-entry recorded at it (the latest skip, entry or
  refusal per setup id, and its `short_check`); a long trigger's are absent. A cell may add `warn: true`, an amber
  pass: **the SSR square is never red** ("SSR · at the ask"). Triggers add `side` and `ssr`. `now` adds both
  blocks for a stock with a short strategy On; its margin square is read only for a short armed or near. A square
  of the short block stops only the short side: while a long strategy that is On could still trade the stock (its
  window open, its next setup allowed, no short held), it stays red and `now.answer` stays `yes`.
- **`GET /api/bot/session`** adds `shorts: {venue, margin_account, equity, hours, live, live_cover, day_cover}` --
  the first four `{ok: true | false | null, text, value}` (memory reads; null is not known, never a pass; on Live
  the margin chip reads IBKR's own figures, and `live` counts the Live short proof's progress), `live_cover` and
  `day_cover` as "Live readiness" below -- or `{venue, error}`.
- **On the desk.** The Bots page asks "Can Nova trade right now?" with the short's chips (Margin account, Equity ≥
  $2,000, Shorts until 15:50, Live shorts: after the Paper proof). The Bot card reads "On for Paper. One bot for both
  sides: each strategy at On trades its own side." with the trade and next-trade lines naming ▲ long / ▼ short.
  The sleeve adds "A short adds: a buy stop always goes in with the entry · a 25% margin cushion · 09:35–15:50, and
  Nova covers what is left at 15:55 · under SSR it sells at the ask · never on a stock you hold." The strategies
  sit in three buckets above their cards -- **On · the bot trades these**, **Eyes · alerts you, Nova never
  trades**, **Off · watches and scores, silent** -- each row with its ▲ LONG / ▼ SHORT tag, its test or read-out and
  its Off · Eyes · On (🔒 On while a short's test has not passed; a short held at Eyes sits there), and the rule
  line under them. Tickers today puts the shorts-only block behind an orange divider. Proposals, Activity and Today
  name the side; "Nova buys" is "Nova trades". On the Trader, Approve, Auto-entry and the bot say the short: BOT
  SHORTS AT, APPROVED with its buy stop and cover, BOT SHORTING / SHORTED / IS COVERING / COVERED / SHORT MISSED.
- **Step 6** adds the Live short proof checklist and Live's 15:55 cover ("Live readiness" below); until the operator
  finishes it and sets `IBKR_SHORT_ENABLED`, Live refuses every short.

## Live readiness: the Live short proof and Live's day cover (ADR 048 step 6, #778 §7)

What stands between a short and Live. In every merged state Live still refuses every short: the operator sets
`IBKR_SHORT_ENABLED` last, and the proof cannot complete until they answer how a Paper day is reviewed (#778,
question 3). Nothing here sets a `.env` value or places an order on its own except Live's day cover, which runs
only while the switch is on.

- **The Live short proof** (owner `short_proof/`): `short-proof.json` in the operator cache, `{schema_version: 1,
  days: {"YYYY-MM-DD": {orders: [order id], symbols: [SYMBOL], first_ts, last_ts}}, drills: {freeze | flatten |
  day_cover | gateway_drop: {passed: Run | null, failed: [Run]}}, reviews: {"YYYY-MM-DD": object}}`, a Run `{at,
  symbol, qty, detail, key, ...}`. Read once into memory (the door reads it under its lock, never the disk) and
  written through a temp file and a rename; an unknown version or a file Nova cannot read is an error, never
  written over, and the proof reads incomplete with the reason. A reset of the Paper ledger never loses it.
  - **Recorded as it happens** (`short_proof/observe.py` on the short runner's loop, `evidence.py` pure): a **day**
    is a Paper practice day (from 04:00 ET) with a filled short entry; the drills, each with a short open on
    Paper: **Flatten** (a fill the ticket's Flatten sent, origin `ticket_flatten`, that covered a short), **the
    15:55 cover** (a `day_cover` fill that covered one), **Freeze all orders** (`kill_switch.trip` hands the
    sweep to `observe.note_freeze`: it passes when every short Paper held kept its buy stop), and **a Gateway
    drop** (IBKR's session dropped while Paper held a short, and when it was back each such short still had its
    buy stop working, or was flat). A drill keeps its first pass and its last `SHORT_PROOF_FAILED_KEEP` runs
    that did not pass, with why.
  - **Complete** with `SHORT_PROOF_DAYS_NEEDED` (3) days the operator reviewed ("no wrong refusal or wrong fill")
    and the four drills passed. `SHORT_PROOF_REVIEW_OPEN` is False until question 3 is answered, so no day can
    be marked and a review written into the file by hand counts for nothing.
  - **The door enforces it** (`short_sale.door.live_proof`, `check._live_proof`): a Live short is refused
    `SHORT_PROOF_INCOMPLETE` right after `live_key`, naming what is missing; a proof Nova cannot read, or a
    reading that fails, is incomplete. Paper and Sim never read it.
- **`GET /api/short-proof`** -> `{schema_version: 1, generated_at, complete, missing: string | null, error: string
  | null, done, total, steps: [{id, label, ok: true | false | null, text, value, seen: "nova" | "operator",
  enforced, how, at}], days: [{date, shorts, symbols, first_ts, last_ts, reviewed}], review: {open, why}}` --
  `done` / `total` count the reviewed days (to 3) and the drills (7 in all). The steps, in the operator's §7
  order: `margin_account` (IBKR shows a margin account by its own figures; null while it cannot say, the paper
  Gateway included), `practice_reset` (the Paper ledger starts at $5,000), `short_tests` (each of the five short
  strategies has a five-year test result), `paper_days`, `drill_freeze`, `drill_flatten`, `drill_day_cover`,
  `drill_gateway_drop`, `live_key` (`IBKR_SHORT_ENABLED`, the operator's, last). `enforced` names what the door
  reads (the margin account, the days, the drills, the switch); the reset and the tests are shown for the
  operator only. `/api/ibkr/status` adds `short_proof: {complete, done, total, error}` (one memory read; a
  failure is `complete: false` with the error).
- **The margin account is IBKR's word.** Account summaries add `ibkr_account_class: "cash" | "margin"` (IBKR's own
  figures: an AccountType or TradingType token, else BuyingPower against cash and excess liquidity) and
  `account_class_source: "override" | "ibkr"`; `account_class` still takes `IBKR_ACCOUNT_CLASS` first. A Live
  short needs `ibkr_account_class: "margin"` (`SHORT_NOT_MARGIN`, saying the override never counts).
- **Live's day cover** (`short_sale/live_closes.py`, every second from the short runner) runs only while
  `IBKR_SHORT_ENABLED` is on: with it off Nova cannot open a Live short, a short opened in TWS is the operator's,
  and Nova places nothing at Live's cover.
  - **When:** a Live short is due by Paper's rule (`hours.cover_due`: outside 09:35-15:55 by the wall clock), and
    its cover goes out only in the regular session, 09:30 to the close (`hours.regular_session`, early closes
    included): outside it IBKR would hold a market order until the next open, and Nova never picks a Live limit
    price by itself.
  - **How:** per short stock, every working Live order on it is cancelled first (`cancel_working`, origin
    `day_cover`), then one protective market BUY covers the short (source `flatten`, `intent: "flatten"`, origin
    `day_cover`), both with `target_venue: "live"` whatever the desk shows. The door admits a Live target for
    `day_cover` alone -- never `margin_call` (IBKR liquidates Live itself) -- only as a cancel or that market
    BUY, only while IBKR is connected, and only while its session is the Live Gateway on a live account
    (`venue_door.live_session_refusal`): the legacy paper Gateway connects too, and its account is not the one
    Live's short is in. The IBKR send skips the desk's practice guard for that one targeted order
    (`ibkr.orders.place_order(targeted=True)`). The door checks the cover under its lock against IBKR's own
    position less the covers already working there (`ibkr/live_book.py`, IBKR's book whatever the desk shows;
    the kill switch's Live sweep reads it too), so a cancel that failed leaves the cover refused, never a buy
    past flat. Nova reads Live's book for the cover and the cutoff only from a Live session; on the paper Gateway
    the short it last saw on Live raises the alarm. A cover stands for its short until IBKR's position shows
    every share it filled (a fill reaches the orders before the position, and a fill in parts can reach it one
    part at a time): while it works, and while it is gone from the working orders but the position does not
    show the shares IBKR's status of it (`live_book.order_state`) says it filled, no second cover goes. It stops
    standing when the position shows the short smaller by at least those shares (then a cover goes for what is
    still short), or when IBKR says it closed with nothing filled (then Nova covers again). The wait counts
    `SHORT_COVER_CONFIRM_SEC` (15 s) from when the cover left the working orders, never from its send (a cover
    can rest through a halt): a cover this session has no status for stands that long, then the position
    decides, and a fill the position still does not show by then raises the alarm (`DAY_COVER_UNCONFIRMED`),
    never a second cover. A refused cover is tried again after `SHORT_CLOSE_RETRY_SEC`. Each step is a
    `day_cover` line on the bot audit stream.
  - **Nova's own Live short entries** (the SELLs its execution record sent as short entries through the Live
    Gateway, `store_orders.short_entries(mode="live")`) lapse as Paper's do
    (`hours.entry_lapsed`: outside the short hours, or a later day than they were placed) and are cancelled,
    whether or not the switch is on.
- **The day cover's alarm** (`short_sale/cover_alarm.py`, in memory): a short due its cover that cannot get one --
  the venue refused it or a cancel before it, a fill IBKR's position does not show, IBKR is not connected or its
  session is not Live's (the short as IBKR last reported it), or Live stands outside the regular session --
  raises one alarm per venue and symbol, `{id: "<venue>:<SYMBOL>", venue,
  symbol, qty, kind: "refused" | "disconnected" | "outside_session", since, updated, error, reason_code, text,
  last_seen}`, cleared when a cover goes out or the short is gone. Paper's and Sim's day cover raises it too. The
  bot session carries `shorts.live_cover` (the switch is on) and `shorts.day_cover: {alarms}`.
- **On the desk.** The Bot card lists the proof's steps under Freeze all orders (`bot/BotShortProof.tsx`, read
  every 15 s): ✓ / ✗ / ? from what Nova sees, "you" on the steps only the operator can do, the count "N of 7
  days and drills", and on hover what to do and whether the door reads it; a backend without the route says
  so. Every desk window shows each alarm as a red bar across the top (`bot/DayCoverAlarms.tsx`, mounted with the
  bot's notices: "DAY COVER · Live · RDYN 416 ▼ SHORT" and what to do), which the window may hide for 10 minutes.
  The ticket locks a Live short while the proof is incomplete or cannot be read ("Short entry locked: the Live
  short proof is not complete (N of 7 days and drills)"). The public demo answers the route with a proof that
  is not complete.

