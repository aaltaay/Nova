# ADR 032 -- The loss breakers are the operator's, per venue

**Status:** Accepted · **Date:** 2026-09-24 · **Amended by:** [[042-one-owner-for-novas-buys]] (the locks lift at 04:00 ET and belong to their venue; commissions counted once)
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
5. **The page.** The bar's two markers are sliders for the desk venue -- dragged, or moved $5 at a
   time with the arrow keys -- saved when let go; loosening Live asks first. "Reset to -$50 / -$200"
   puts the venue back on the defaults, and a venue on the defaults keeps no pair of its own
   (`custom: false`). The Account page's Risk block draws the same pair.

## Consequences

- The operator can keep testing on Paper after a bad morning without touching Live's limits.
- On Live the thresholds are the operator's to loosen; the confirm is the only guard, and the
  audit stream records it.
- Nothing about who is gated changes: the breakers still flatten through the same door and still
  gate manual buys with the all-stop's day lock.

## Live daily P&L source (#664)

Live compares IBKR's `reqPnL(account).dailyPnL`, not an overnight holding's
lifetime unrealized gain or loss. `ibkr.day_pnl` owns one read-only subscription
for the current READY IB instance, generation and selected account. It starts
on READY on the IB loop, replaces the old scope on reconnect/account changes,
and accepts only matching subscription events. Disconnection, stale callbacks,
request errors, non-finite values and IBKR's unset-double sentinel invalidate
its value; repeated READY wiring does not duplicate it. Reads are in-memory
and cannot issue broker requests from the HTTP loop.

Until a valid daily value arrives, retain the existing account-summary
`RealizedPnL + UnrealizedPnL` as an explicitly labelled fallback, including why
daily P&L is unavailable and that the fallback includes lifetime open P&L.
No usable broker figure means unknown, never zero. Commissions are already in
both figures and are never subtracted again; an unreadable commission ledger
continues to hold new Live bot entries independently.

IBKR owns its daily reset, configured in TWS. The API does not supply the reset
time, so `reset_time` stays null and the meter states the broker-owned reset
semantics. Nova does not infer a reset from a change in P&L. The existing 04:00 ET
breaker-latch boundary and practice-ledger day are unchanged. This fixes the
Live breaker source; it grants no Live bot authorization and needs no broker
mutation to verify the subscription and fallback contracts locally.
