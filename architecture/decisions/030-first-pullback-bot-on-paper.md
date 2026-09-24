# ADR 030 -- The first-pullback bot trades Paper and Sim; the read-out gates Live

**Status:** Accepted · **Date:** 2026-09-24 · **Amended by:** [[031-a-scanner-for-every-setup]] (the bot trades the chosen setup)
**Amends:** [[027-bot-playbook-readout-gate]] decision 3 (the read-out gates Strategy on every venue)
**Builds on:** [[022-setup-scanner-tape-gate]] · [[029-setup-templates-eyes-journal]] · [[020-three-venues-one-feed]]
**Decided by:** the operator, 2026-09-24 ("When I'm on paper, I cannot activate the button for the
bots" -- then, of three choices, "Paper/Sim skip it + build")
**Resolves:** #514

## Context

ADR 027 closed Activate at Strategy until the pre-registered first-pullback read-out
passes (Bot-Trading-Plan §2g: 50 triggered setups with the tape at go, average net R
above +0.2 and above blind / wait). The gate held on every venue, Paper included, and
nothing in Nova placed a trade when a setup triggered (#514) -- so even an open gate
would have lit an "Active" bot that did nothing.

On the desk that evening the read-out stood at 0 of 50: the scanner had armed five
setups since it started and one had triggered, blind, because a go verdict needs Nova
to hold the name's Level 2 at the trigger. At that pace the gate stays shut for weeks,
and the operator's definition of done is evidence from the bot trading on Paper.

The bot's Paper trades cannot move the read-out: the read-out is computed from
`setups.db`, which the setup scanner writes from bars and the tape whether or not
anything trades. Paper and Sim are fake money.

## Decision

1. **The read-out gates Live only.** On Paper and Sim (`sim.mode.is_practice_venue`)
   Activate at Strategy, raising to Strategy and every L2 fire -- Nova's own bot and
   an external brain alike -- skip the read-out. A venue Nova cannot read counts as
   Live. `bot/gates.py` owns the rule (`readout_required`, `readout_open`); the
   `readout` gate reads `ok: true` there with `detail.waived: true` and the venue, and
   `GET /api/bot/session` adds `readout_required: boolean`. A Strategy bot left active
   when the desk moves to Live with the read-out still closed is deactivated within a
   second, on the audit stream ("Live waits on the first-pullback read-out").

2. **Nova's own first-pullback bot** (`backend/bot/first_pullback/`). When the bot is
   Active at Strategy with the first pullback chosen, on Paper or on Sim at the live
   edge, it plays the template in play's setups:
   - **Entry.** A first pullback (not a second: the read-out counts only first
     pullbacks) that triggers on the live feed with the tape at **go** gets one BUY
     limit at the entry the scanner scored at the trigger (one cent over the trigger,
     or the bar's open when it gapped over). Size: the sleeve's max shares, cut to the
     sleeve's dollar budget. A limit that has not filled within the sleeve's working
     TTL is cancelled: a **miss**, recorded as one. It never chases. Only the bot's
     own names (its allowlist) are considered; another name's trigger stays on the
     scanner's record alone, so the timeline is not flooded with blind triggers.
   - **Exits.** Practice venues take no brackets, and the execution door refuses a
     second SELL of shares already sent (`OVERSELL`), so the bot rests one exit
     and watches the other: after the fill a SELL limit rests at target 1, and the
     bot watches the setup's stop on IBKR's Last (a print that sets a price). A
     print at or under the stop, or the **time stop** 15 minutes after the fill
     (the scoreboard's window), cancels the target and sells with a limit a few
     cents under the bid -- twice at most -- then the protective flatten, which a
     locked padlock still sends. A live version would use IBKR's own bracket.
   - **Gates.** Every gate the bot API meets: the level, Activate, the padlock, the
     allowlist and a held depth line, the template's window and one trade a day, the
     day lock, the kill switch, the working-order block and the budget. The entry is
     audited as `buy_setup_limit` -- a buy kind, so it counts toward the day's cap --
     which no brain may send (it carries the scanner's price, not a preset). An
     entry cancelled unfilled gives the day back: nothing was bought.
   - **The session.** The bot claims the L2 session as brain `nova-first-pullback` and
     heartbeats while it plays, so an external brain cannot fire beside it (and while
     one holds the session, the bot skips with that reason). Deactivate stops new
     entries; a trade already on keeps its stop, target and time stop until it closes.
     KILL, Flatten, or closing the position by hand ends it -- the bot sees the
     position gone and cancels what it left working. A target cancelled by someone
     else leaves the stop and the time stop in force, said on the timeline.
   - **The record.** Every step is on the bot audit stream as `bot_trade` (`skipped`,
     `missed`, `filled`, `closing`, `closed`, `note`, `error`) with the setup id, so a
     trade joins its `setups.db` row. `GET /api/bot/session` adds `trade`: the
     current or last trade -- `{setup_id, symbol, venue, venue_day, template_id,
     template_rev, state: "entering" | "open" | "exiting" | "closed" | "missed",
     qty, trigger, entry_planned, stop, target1, risk, entry_order_id,
     entry_fill_price, entry_filled_ts, target_order_id, exit_order_id,
     exit_price, exit_reason: "target" | "stop" | "time" | "outside" | null,
     closed_ts, slippage, r, note}` -- and `runner: {brain_id, playing, reason}`,
     kept in `bot-session.json`
     (schema 4, an optional key) so a restart resumes managing it. `r` is gross,
     `(exit - fill) / risk` with the setup's own risk, so it sits beside the
     scoreboard's R; the practice ledger holds the net.

3. **Live stays out of it.** Nova's bot places nothing on Live. Live keeps ADR 027's
   read-out gate, and taking the bot live needs gate 2 as well (100 Paper trades with
   expectancy within ~30% of the read-out and slippage measured) and an operator
   decision. `auto_live` remains NO-GO.

## Consequences

- The operator can Activate the bot on Paper today, and it trades the first pullback
  wherever it holds the Level 2 of an allowlisted name that triggers with the tape at
  go. The Paper evidence gate 2 asks for accrues from the first go trigger, beside the
  read-out rather than after it.
- An active bot places real (practice) orders: the proposals inbox keeps proposing, so
  the operator placing the same setup by hand doubles the position. The timeline says
  when the bot entered.
- Not built here: the bot on a replayed Session Record (the Sim eyes off the live
  edge), the research's half-off-at-target-1 and 9 EMA exits, and tape-read exits.
- A watched stop is only as good as the loop and the feed: a stop that prints while
  the backend is down is not taken until it is back (the time stop too). On fake
  money that is a stated limit, and the reason Live would use IBKR's bracket.
- `CHOSEN` numbers (`constants_bot.py`): the 15-minute time stop, a trigger older than
  5 s is skipped, the heartbeat every 5 s, the bot's loop every 0.5 s, two tries at
  the bid before the protective flatten.
