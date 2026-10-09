# ADR 052 -- The bot trades a Sim replay, and the chart draws the Sim eyes

**Status:** Accepted · **Date:** 2026-10-09 · **Amended:** 2026-10-09 (#816: the bot's entry carries its own expiry -- Consequences; #815, below: Auto-entry, Approve, Nova's exit and the past setups on a replay)
**Amends:** [[030-first-pullback-bot-on-paper]] ("not built here: the bot on a replayed Session Record") · [[029-setup-templates-eyes-journal]] (its 2026-09-24 amendment: a loaded download is re-read, no longer played back from the journal) · [[042-one-owner-for-novas-buys]] (Activate's `BOT_REPLAY_DESK` refusal; the day's count on a replay) · [[036-the-bots-read-on-one-stock]] (the read on a replay desk) · [[037-who-trades-the-stock]] (Bot on a replay)
**Builds on:** [[019-practice-fills-on-replayed-sessions]] · [[020-three-venues-one-feed]] · [[046-sim-replays-the-massive-flat-files]]
**Decided by:** the operator, 2026-10-09 (#814): "why bots dont work in simulator mode? we need to make them work like paper trading, just watch out of data leaks, cuz expect the user to unwind go backward in time and forward in time.. etc. i wanna see the eyes/strategy on the charts you know.." The design is the agent's, under the operator's standing grant: fake money, no Live path touched.

## Context

On the Sim desk off its live edge the bot did nothing, for four reasons:

1. `bot.activation.venue_block` refused it (`BOT_REPLAY_DESK`: "the bot trades live triggers only").
2. The bot's loop heard only the live setup scanner, which proposes and triggers nothing on a replay desk.
3. With a historical window loaded -- a Massive window, the way the operator practises past days (ADR 046) --
   the Sim eyes ran no lanes at all: they played back the live journal of that day, so no trigger existed.
4. The Trader's chart drew nothing from the Eyes on a replay desk: the stock read was switched off there,
   because its backend read the live engine, the wall clock and the whole day's bars -- after the playhead too.

The Sim scratch account already filled on the replay's prints and unwound when the playhead went back
(ADR 019, ADR 020 decision 3), so the missing part was the bot's side of time travel.

## Decision

1. **One source on a replay.** With a replay loaded -- a Session Record, or a historical window -- the Sim eyes
   run today's templates over it (`eyes.sim_target`, `eyes.sim_eyes`): the Setups board, every setup card,
   the Trader's chart and Nova's bot read those lanes, and the scratch account fills on the same prints.
   A historical window becomes the lanes' recording (`eyes.history_recording`):
   - prints with the side the window's NBBO gives each one -- the last quote strictly before the print,
     the Sim tape's own rule;
   - the NBBO as a **one-level book**, sampled every 0.5 s inside the downloaded spans as the live tape feed
     samples a held line -- not Level 2: a wall behind the inside is invisible, and the board says so;
   - the bar archive's one-minute bars of the day when Nova has them, else the window's own candles;
   - an IBKR download has no bid or ask: no book, no sides, the tape gate reads blind there and nothing
     goes -- said on the board, never guessed.
   With nothing loaded off the edge the board stays the live journal played back (ADR 029 amendment).
2. **Triggers the playhead plays across.** A playing lane's go trigger on the replay goes to the trigger
   listeners -- Nova's bot -- stamped with the replay's key (the scratch account's own, `sim.practice.loaded`),
   only when it is no older than the bot's 5 s at the playhead on a forward step. A rebuild (a rewind, a
   template change, another replay) and a jump forward hand the bot nothing they passed. The bot takes a
   trigger only from the feed the desk shows: the live scanner's on Paper and at the live edge, the Sim eyes'
   for the replay loaded now.
3. **The bot trades a replay like Paper** (`bot.replay_desk`). Activate is refused on Sim off its edge only
   with nothing loaded. Every rule stands -- the level, the strategy's rules, the tape at go, NOT A TRADE,
   the padlock, the kill switch, the window, the size, the short check (which already reads a replay's
   recorded borrow, halts and SSR at the playhead). What changes is what the rules read:
   - **the clock is the playhead**: the trigger's age, the entry's working TTL, the time stop and every exit
     wait run on the Sim clock, which stands still while it is paused (heartbeats keep the wall's);
   - **quotes and the book** are the replay's at the playhead (`sim.practice.reference`), the ones its
     orders fill against; the depth-line rule is met by the replay's own book (recorded Level 2, the
     window's NBBO, or a book Nova recorded that day), beside the open historical Level 2's slot (R44);
   - **the day's entries** are this run's on the replay -- the entries sent before the playhead on it --
     never the audit stream's, which keeps lines a rewind took back and lines from another play of the
     same day; a line written on a replay carries `replay: {key, playhead_ts}` and counts nowhere else;
   - **the flush exit** reads the Sim eyes' flow readings.
4. **The bot goes back with the playhead.** It checkpoints what it remembers -- its trade, its working
   orders, the shares it holds, the replay's entries -- whenever that changes, stamped with the playhead.
   When the playhead goes back (the scratch account unwinds and says so through `bot.rewind`, or the bot
   sees the playhead earlier than before) it takes back what it remembered at the new playhead: a trade
   sent later never happened, a fill later is not filled. Only the replay's own part goes back -- its trade,
   its orders, its shares: the session has one trade slot, and a trade made elsewhere (Paper, the live
   edge, another replay) is never touched. An order of its own the ledger still holds but the restored
   trade does not know (sent between two checkpoints) is cancelled. Every rewind gives the bot's
   idempotency keys a new run tag, so a setup the playhead plays across again is sent again. Another
   replay starts the account over and the bot's trade on the old one is retired `rewound`; so is a replay
   trade this process did not make (a restart: the scratch account does not survive one) -- each said on
   the timeline. A trade made on a replay is managed only while the desk shows that replay.
5. **Who trades.** On a replay a stock can be Bot (Entry and Exit Nova): the Trader's Who trades row shows on
   a replay, a Session Record's too, on the playhead's clock. Auto-entry, Approve and "Nova takes the exit"
   stay on Paper and at the live edge (`STOCK_MODE_REPLAY`), and the switch says so before the press
   (`locks.modes`).
6. **The chart on a replay** (`stock_read.replay_read`). The read is the replay's at the playhead: the Sim eyes'
   setups and the plan built from them, the day's levels from the Sim chart's own candles up to the playhead,
   the daily map from the days before the replayed one, the bot's trade on this replay. What only the live
   feed knows -- Level 2 and the tape sensors, the flow score, pulls, rvol, why it's moving, HOD Momo, borrow,
   halts, dilution, LULD, the boards -- is unknown there. A cached read is served only for a playhead at or
   after its own. The day routes (past setups and their aftermath, the decisions timeline) read whole days and
   answer nothing on a replay desk; the history reads only the days before; the flush reading is blind.
7. **Never after the playhead.** While a rewind waits for its rebuild (at most every 2 s), the board, the
   cards and the chart's read say they are catching up instead of showing the lanes as they stood later.
   The Trader draws a replay read only when it was made at or before the playhead it shows, and reads again
   the moment the playhead moves to another 5 s, so a rewind never shows the later read while the next one
   comes. A replay still trips no breaker (ADR 042 item 8).

## Rejected

- Re-deriving the bot's trade from the ledger after a rewind: the ledger holds orders and fills, not the
  setup, stop, target and risk the trade carries. Checkpoints keep them; the ledger still decides what filled.
- Keeping the bot's replay memory in `bot-session.json`: it would outlive the scratch account it follows.
- Counting a replay's entries from the audit stream: a rewind, or a second play of the same day, would count
  entries that never happened in this run.
- Keeping the journal playback for a loaded download and running hidden lanes for the bot: the bot would trade
  triggers the board does not show.
- Drawing the live read on a replay with its wall-clock facts: today's borrow, news or Level 2 beside a past
  moment is a leak, not an answer.

## Consequences

- The operator can load a Massive day, turn the Bot on in Sim, set the stock to Bot and watch the Eyes draw
  the setups on the chart and the bot trade them on the scratch account -- and scrub back to watch it again.
- A Massive window's tape gate reads the NBBO only; walls behind the inside and hidden sellers past the
  top of book are not seen, so a go there is weaker evidence than a recorded Level 2's. The board says
  which book it reads.
- ~~A jump forward over a working bot entry lets the scratch account match it on the prints the jump crossed
  before the bot's working TTL cancels it (the matcher runs on the jump; the TTL on the next tick). At play
  speed the TTL holds as on Paper. A per-order expiry on practice venues would close it (follow-up).~~
  **Closed (amendment 2026-10-09, #816):** the bot's entry on a replay carries its own expiry --
  `ExecutionCommand.good_for_sec` = the sleeve's `working_ttl_sec`, which the practice broker turns into
  the row's `expires_ts` (the earlier of the TIF's close and placement plus the seconds). A jump past that
  second never fills the entry on the prints it crossed: it ends `Expired` (`PRACTICE_GOOD_FOR_EXPIRED`)
  at its own second and the trade `missed`, and a scrub back before it restores it working. A cancel that
  reaches an order already past its expiry records the expiry, so the bot's own TTL cancel arriving first
  ends the same way. Live refuses the field (`GOOD_FOR_LIVE`); IBKR's GTD would need its own ADR. Paper and
  the live edge keep the bot's TTL cancel alone. Left as it was: when the bot's tick runs before the Sim
  feed's match after a jump, a print inside the TTL that the match has not reached yet does not fill the
  entry -- the same as before this amendment.
- Auto-entry, Approve, "Nova takes the exit" and the past setups' aftermath on a replay were follow-ups; the
  amendment below builds them (#815).
- Nothing here touches Live: the bot never trades Live, and `auto_live` remains NO-GO.

## Amendment 2026-10-09 -- every Nova mode on a replay, and the setups that ended (#815)

**Decided by:** the operator's #814 ask ("make them work like paper trading ... watch out of data leaks") carried
to the modes decision 5 left at Paper, under the same standing grant: fake money, no Live path touched.

1. **Auto-entry, Approve and "Nova takes the exit" trade a loaded replay** (`stock_mode.replay`), as decisions 2-4
   let the bot. The stock-mode runner hears the Sim eyes' triggers, takes one only from the feed the desk shows
   (decision 2), and runs on the venue clock -- the playhead on Sim: a trigger's age, an entry's working TTL and
   the exit's closed minutes run on it and stand still while it is paused. Its rules are unchanged.
2. **A replay's trades and approvals are the replay's.** They carry its key (`replay_key`) and live in memory
   beside the persisted trades, never in `stock-mode-trades.json`: the scratch account they trade on does not
   survive a restart. One made on a replay acts only while the desk shows that replay; a trade or approval made
   at the live edge waits while the desk replays -- it is never managed against the replay's ledger.
3. **They go back with the playhead.** The runner checkpoints the replay's trades, approvals and entries whenever
   they change (and after each act of the operator's on the switch), stamped with the playhead. When the playhead
   goes back (`bot.rewind` tells stock mode too, or the runner sees it earlier than before) they return to what
   they were at the new playhead: a trade sent later never happened, an approval made later was never made, a
   fill later is not filled. An order of a replay trade the ledger still holds but the restored trades do not
   know is cancelled. Each rewind changes the stock-mode idempotency keys' run tag, so an approved setup the
   playhead plays across again is sent again. The switch itself is the operator's setting, like Activate: it
   does not go back. Another replay starts the account over and the old replay's trades and approvals go with
   it, on the timeline.
4. **One daily count.** Auto-entry's entries on a replay are this run's -- sent before the playhead, a miss given
   back -- and share the cap with the bot's (`entry_rules.today`); Approve's are counted, never capped.
5. **Who trades on a replay.** With a replay loaded every mode is open (`locks.modes` all null). With nothing
   loaded off the edge there is nothing to trade: Auto-entry, Approve and Nova's exit are refused
   `STOCK_MODE_REPLAY` with that reason; Bot stays open (its Activate says why, decision 3).
6. **The setups that ended, on a replay** (`eyes.sim_past`). The Sim eyes fold the lines their lanes write into
   episodes as they are written (`eyes.episodes`, the live journal's fold), a fold per rebuild, so it holds only
   the lanes' own lines up to the playhead -- never the day's journal file, which on a replay holds every play of
   the day and journals nothing a rebuild passed. "What price did next" (`eyes.aftermath`) reads the replay's
   one-minute bars completed by the playhead: a window still open reads `pending`, never the minutes after it.
   `GET /api/stock-read/{symbol}/past-setups` answers them on a replay desk (`replay: true`); while a rewind waits
   for its rebuild it answers none and says it is catching up. The Trader draws them on a replay only from a read
   made at or before the playhead it shows, and reads them again the moment the playhead moves to another 5 s.

**Rejected.** Persisting a replay's stock-mode trades with the others: they would outlive the account they trade
on, and a restart would manage orders that no longer exist. Folding the day's journal up to the playhead for the
past setups: a rewound play leaves lines of a later moment in it, and the replay's own rebuild journals nothing it
passed, so the journal is neither complete nor free of what came later.
