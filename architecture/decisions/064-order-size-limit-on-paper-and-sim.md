# ADR 064 -- Your own order size limit on Paper and Sim

**Status:** Accepted · **Date:** 2026-10-20
**Amends:** the operator's decision on #444 (2026-09-22, PR #480: "keep enforcing one quantity for the live so we never mess it up, and remove that restriction for paper and sim"). The test quantity gate still binds Live only; Paper and Sim now have an optional limit of the operator's own, off until set.
**Related:** [[056-one-daily-loss-limit]] (the limit sits beside it in Settings > Loss limits and refuses in the same way) · [[007-centralized-trading-execution]] (the one door) · [[048-short-selling]] (a cover is a close)
**Decided by:** the operator, 2026-10-20, answering four questions in turn:
- "Do you now want an optional size limit on your own hand orders on Paper and Sim?" -- **Yes, build it.**
- "Which limit or limits should it have?" -- **Both, each optional** (the preview: *Order size limit*, columns Paper and Sim, rows Max shares and Max risk at stop, "empty box = no limit").
- "If the dollar-risk limit is on and you send a buy with no stop attached, what should Nova do?" -- **Refuse it and say why.**
- "What should the boxes hold when the feature first ships?" -- **Empty, all off.** Nova's code holds no numbers.

## Context

On Paper and Sim the operator's hand orders had no size limit: the order ticket sends any quantity, and the Trader's plan box only *suggests* a size from the venue's risk per trade. The daily loss limit (ADR 056) stops new buys after a dollar loss, so it can never stop the one oversized first order that makes the loss. Live never had the gap: it sends at most `IBKR_QTY_CAP` shares (1 by default) and arms only with the operator's PIN.

## Decision

1. **Two optional numbers per practice venue.** Settings > Loss limits, under the daily loss limit, holds **Order size limit**: **Max shares** (the most shares one order may buy or short) and **Max risk at stop** (the most one order may lose at its stop: shares x |entry - stop|, in whole dollars), one column for Paper and one for Sim. An empty box is no limit; every box ships empty. Live has no column: Live keeps its test quantity gate and its PIN, unchanged.

2. **Your own orders that open or add, and nothing else.** The execution door reads the limit for every `place` or `bracket` from source `manual` -- the ticket, the hotkeys, the plan box's Approve -- on Paper and Sim that opens or adds: a BUY that covers no short, or a SELL with `short_entry`. Selling what you hold, a BUY that covers a short, exit pairs, cancels, replaces, Flatten and KILL never meet it. Bot orders (source `bot`: the bots, Auto-entry, the localhost bot API) never meet it; the bots keep their own sleeve caps.

3. **Refused in the limit's words, never cut.** An order over a limit is refused before any send, its reason on the ticket's Last line (or on the approval), naming the venue, the limit, the order's own figure and where to change it: "Paper allows at most 500 shares per order; this order is 800 shares. Lower the size, or change Max shares in Settings > Loss limits. Selling what you hold, covering a short, cancels, Flatten and KILL still work." Codes `ORDER_SIZE_LIMIT_SHARES`, `ORDER_SIZE_LIMIT_RISK`. Nova never quietly sends a smaller order than the one asked.

4. **No stop, no known risk.** While Max risk at stop is set, an order that carries no protective stop is refused `ORDER_SIZE_LIMIT_NO_STOP` ("this order has no stop, so its risk is unknown. Attach a stop, or clear Max risk at stop..."). Only a bracket carries one (the ticket's stop-loss leg, Approve's plan, a short's buy stop); a plain place's `stop_price` is a stop order's own trigger, not a protective stop. Max shares alone needs no stop.

5. **Approve says it at Approve.** The plan box's Approve meets the same check when the operator clicks it, so a plan over the limit is refused then, not hours later at the trigger; a limit lowered after the approval is the door's to refuse at the trigger, and the approval is withdrawn with the reason.

6. **One order at a time, when it is placed.** Each order is read alone; two orders under the limit may together hold more. Moving a working order's stop later is never refused here: a stop move manages a trade already open.

7. **A setting Nova cannot read refuses, it is not read as off.** The file is `order-size-limit.json` in the operator cache (owner `execution/size_limit/settings.py`). With no file every limit is off. A file this build cannot use -- unreadable, another version, a value out of its rule -- refuses new hand orders on Paper and Sim `ORDER_SIZE_LIMIT_UNREADABLE`, and Settings says so, until any save writes a fresh file. A limit that silently vanished would be the one the operator trusted (the kill switch's latch reads the same way).

## Consequences

- The 2026-09-22 decision's Live half stands; its "no cap on Paper / Sim" now reads "no cap unless you set one".
- Nothing changes for anyone until the operator types a number.
- A hand order with no stop cannot be sent on a venue whose Max risk at stop is set -- including a Market buy, which never carries a stop. That is the operator's choice: without it, any order without a stop gets around the limit.
- The ticket does not pre-check the limit; the door's refusal is the one source of the words.
- Owner `backend/execution/size_limit/` (`settings`, `gate`, `routes`); UI `frontend/src/order_size_limit/`. Schema: `architecture/schema/execution.md`, "Your own order size limit on Paper and Sim".
