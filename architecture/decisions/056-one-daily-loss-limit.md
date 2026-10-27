# ADR 056 -- One daily loss limit, in Settings, for you and the bots

**Status:** Accepted · **Date:** 2026-10-15
**Supersedes:** [[032-loss-breakers-per-venue]] (the bot trip and the all-stop are gone) · [[016-bot-localhost-api]] decision 6 (breakers on whole-account Day P&L)
**Amends:** [[042-one-owner-for-novas-buys]] (decisions 2, 3 and 8: no bot trip to re-enable, no `bot_trip` / `day_lock` gates; the `loss_limit` gate replaces them) · [[044-one-bots-page]] (decision 1: a trip no longer turns the Bot switch off; the breaker bar leaves the Bots page)
**Decided by:** the operator, 2026-10-15, after the bot trip sold a manual Paper buy 3.4 seconds after it filled (WETO, 09:32 ET: 10,000 shares bought by hand, the day read -$451.03 against the -$405 bot trip, the trip sold all 10,000 at market for -$550, which took the day to -$600.35 and fired the -$500 all-stop, locking Paper's buys until 04:00 ET; raising the all-stop afterwards did not lift the lock). The operator's words, in order:
- "I don't think we should let a loss breaker ever happen ... I just got this message even though I moved the breaker."
- "We're in the middle of the trade, and you're forcing a bot, for absolutely no reason, to sell because it went below a certain amount. I think we have enough strategies to know that it's time to sell."
- "I don't want to sell just because we are down ... and is the loss only in 24 hrs loss or one week loss, how is it even counted!"
- "We should just have a master in the user configuration, not in the bot ... Let's have a check mark: do we want this or do we not? ... auto pause, auto sell, or not?"
- "Let's switch it to a dollar amount and explain it as what we're selling, literally ... no confusion ... doesn't cause false triggers." On a stock bought a decade ago: it must never count.
- "A human and a bot should be able to act the same, so just say 'daily loss limit' ... It's one limit for both."
- "Put it under Sensors. And remove that from the bot ... make sure you cleanly disconnect everything else."
- "A bot can still execute a sell order based on the strategy, so don't confuse those."

The form was iterated as mockups on 2026-10-15 (v1 to v4); v4 is the one built.

## Context

Two breakers watched the whole account's day P&L: the bot trip (flatten everything, the Bot switch off at Eyes, latched to 04:00 ET) and the all-stop (flatten everything, lock bot and manual buys on that venue to 04:00 ET). Their thresholds lived per venue on the Bots page. Four things were wrong with them:

- **Named for the bot, acting on everyone.** The "bot trip" sold positions the operator opened by hand, while no bot held any.
- **Selling an open trade on a mark.** They counted open positions at their last price, so a fresh 10,000-share entry crossed -$405 on a 4-cent dip plus commissions.
- **One trip firing the other.** The bot trip's own market sell turned -$451 into -$600 and fired the all-stop a second later.
- **A lock the slider could not lift.** Moving a threshold never cleared a fired breaker, so the order ticket kept refusing after the operator moved it.

The desk also said "Bot sold 10,000 shares of WETO": the voice counted a `bot_trip` close as a bot trade.

## Decision

1. **One limit, one place.** Settings > **Loss limits** (a left-menu entry under Sensors) holds the whole feature: **Daily loss limit** in dollars, and three checkboxes -- **Warn me** (on), **No new buys** (on), **Auto sell** (off; "sell what's held"). One setting for every account: Live, Paper and Sim. The Bots page, the Account page and the bot session carry no loss limit.

2. **What it counts, literally.** Trades opened today, yours and the bots' alike: what was lost on the ones closed, what the open ones are down right now at the account's own mark, and commissions. "Today" starts at 04:00 ET. A stock the account already held at 04:00 ET never counts, even if you trade more of it today, and is never sold. Each account is counted on its own: a Paper loss never locks Live. On a Sim replay nothing is counted (a replay's P&L is not today's). An unknown figure (no mark for an open position, an account that cannot be read) is a stated unknown and never acts; an unknown commission counts as unknown in words but the rest still counts, since a commission only adds to the loss.

3. **No false triggers.** The loss must stay past the limit for 10 seconds in a row before anything happens. One reading back under it, or an unknown reading, starts the 10 seconds again.

4. **What each checkbox does at the limit.**
   - **Warn me:** a notice in every desk window and a voice line at 80% of the limit, once per account per day. Reaching the limit itself is always said, whatever is checked: no block is ever silent (ADR 042).
   - **No new buys:** that account refuses every order that opens or adds to a position -- a buy, a short entry -- from you and from the bots, until 04:00 ET. Selling what's held, covering a short, cancels, Flatten and KILL always work.
   - **Auto sell:** that account sells every position opened today, at market, through the execution door (source `flatten`, origin `loss_limit`, the account named as `target_venue`), after cancelling the working orders on those stocks. Positions held before today are never sold.
   With all three off, the limit only counts.

5. **Changing the setting re-reads it.** Any change -- the dollars or a checkbox -- clears today's warning and trip on every account; if the loss is still past the new limit for 10 seconds, it trips again. Raising the limit or unchecking No new buys lifts the lock at once.

6. **A bot's own sells are untouched.** A bot's strategy exits -- its stop, its targets, its flush exit, its time stop, the Live Trader bot's closes and its 15:55 sell-all -- are the bot's, and nothing here holds or replaces them. The limit never turns a bot off; No new buys only refuses its new entries.

7. **Removed.** The bot trip and the all-stop (`bot/breakers.py`, `bot/breaker_limits.py`, the breaker loop, the bot trip's latch and re-enable, the all-stop's day lock in `bot/buy_lock.py`), the `breakers` / `soft_breaker` / `day_lock(s)` session fields and the `PATCH {breakers}` door, the `bot_trip` and `day_lock` gates and `BOT_TRIP_LATCHED`, the Bots page's breaker bar and status, the Account page's Risk pair, and the breaker notices. A bot session saved with the old fields loads with them dropped. Old orders keep their `bot_trip` / `all_stop` origins and are labelled as before; nothing sends them again.

## Amendment 2026-10-27 -- the day walks back over weekends and holidays (#1090)

**Decided by:** the operator, 2026-10-27, on #1090 (option 1: "walk back like the rest of the desk").

"Today" (decision 2) and "until 04:00 ET" (decision 4) are the trading session the rest of the desk already uses
(`market.session_key_et`, ADR 008 amendment 2026-10-17), not the calendar day: a weekend or NYSE holiday belongs to
the last exchange day before it. A Friday's count, warnings and trip hold through the weekend and end at the next
exchange day's 04:00 ET -- Monday, or Tuesday after a Monday holiday. Before this, the day was the plain calendar
clock and Saturday 04:00 ET cleared a Friday lock and started a new count at zero. Weekdays are unchanged. Owner:
`loss_limit/state.desk_day`; schema `architecture/schema/loss-limit.md` ("The desk day").

## Consequences

- WETO's morning cannot repeat: a manual entry is never sold by a limit unless Auto sell is checked, and then only past the dollar line for 10 seconds.
- With Auto sell off (the default) a forgotten position keeps its loss; Warn me is what says so, at 80% and at the limit.
- The voice and the Orders table name a limit's close "Loss limit", never "Bot sold".
- One number for every account means Live and Paper share it; Live's 1-share cap keeps Live's dollars small either way.
- The schema is `architecture/schema/loss-limit.md`.
