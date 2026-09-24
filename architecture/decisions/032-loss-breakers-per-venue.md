# ADR 032 -- The loss breakers are the operator's, per venue

**Status:** Accepted · **Date:** 2026-09-24
**Amends:** [[016-bot-localhost-api]] decision 6 (the -$50 / -$200 breakers were fixed product thresholds)
**Decided by:** the operator, 2026-09-24 -- on the Risk Sleeve's loss-breaker bar: "I want us to be
able to change this stuff ... move that slider ... and make sure these changes are persistent in a
db, not when we reboot it revert back to default." The bounds and the per-venue split are the
agent's, under the operator's standing grant; each has the operator's veto.

## Context

ADR 016 fixed the two loss breakers on the whole account's day P&L: the bot trip at -$50 (flatten,
the bot to L0, re-enabled the same day) and the all-stop at -$200 (flatten, bot and manual buys
locked until the next ET midnight). The Bots page drew them locked. On Paper the operator's day
reached -$56.63, the bot trip fired, and there was no way to move it.

The sleeve the page already let the operator change (max shares, budget, working TTL, extended
hours) is saved to `bot-session.json` in the operator cache and read back at every start; it does
survive a restart. What did not exist was any way to change the breakers.

## Decision

1. **Two thresholds per venue.** The bot session keeps `breakers: {VENUE: {soft_usd, hard_usd}}`
   for `live`, `paper` and `sim`; a venue with none reads -$50 / -$200. The breaker loop compares
   the day P&L with the desk venue's own thresholds (`bot.breaker_limits`), so loosening Paper
   never loosens Live. A venue Nova cannot read uses Live's.
2. **Bounds.** The bot trip between -$5 and -$1,000, the all-stop between -$10 and -$5,000,
   the bot trip always above the all-stop; values snap to $5. A refusal is `400
   BOT_BREAKER_INVALID` with the rule in words.
3. **What moving one does not do.** A breaker that already fired stays fired: moving the bot trip
   never clears its latch (the operator re-enables it as before), and moving the all-stop never lifts
   a day lock.
4. **Saved, and saved whole.** `PATCH /api/bot/session {breakers: {venue?, soft_usd?, hard_usd?}}`
   writes the session file like every other session field; the session and proposals files are now
   written through a temp file and a rename, so a crash mid-save can never leave half a file (which
   would have read as an error, and the page as defaults). Each change is on the audit stream
   (`breakers`, the venue, before and after).
5. **The page.** The bar's two markers are sliders for the desk venue; loosening Live asks first.

## Consequences

- The operator can keep testing on Paper after a bad morning without touching Live's limits.
- On Live the thresholds are the operator's to loosen; the confirm is the only guard, and the
  audit stream records it.
- Nothing about who is gated changes: the breakers still flatten through the same door and still
  gate manual buys with the all-stop's day lock.
