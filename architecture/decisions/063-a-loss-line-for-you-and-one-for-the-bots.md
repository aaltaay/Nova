# ADR 063 -- A loss line for you and one for the bots, inside each account

**Status:** Accepted · **Date:** 2026-10-20
**Amends:** [[056-one-daily-loss-limit]] (decision 1: one line becomes three; decision 4: what No new buys and Auto sell do when a side's line is crossed; decision 2's "yours and the bots' alike" stays true of the Account line)
**Decided by:** the operator, 2026-10-20, choosing among options put to them before any code was written:
- Which lines: **You + Bots + Account**, one set of numbers for Live, Paper and Sim (each account still counted on its own) -- not one number per account, and not both.
- On a trip: **only that side** -- a crossed Bots line stops only the bots' entries and, with Auto sell, sells only the bots' shares opened today; a crossed You line does the same for the operator's; the Account line still stops and sells everyone.
- The checkboxes: **one set** (Warn me, No new buys, Auto sell) for every line.
- A trade one side opened and the other closed: **whoever opened it** owns it.

## Context

ADR 056 gave each account one daily loss line counting the operator's trades and the bots' together. On Paper the operator, the strategy bots and the Live Trader bots trade one account, so a bot's ordinary losing day could reach the line and stop the operator's buys, and the operator could not set a tight line on hand trading without stopping the bots at the same number.

## Decision

1. **Three lines per account.** Settings > Loss limits keeps the daily loss limit -- now the **Account** line, counting every trade opened today as before -- and adds **Your trades** and **Bots' trades**, each in whole dollars or empty for no line. The same three numbers apply to Live, Paper and Sim; each account is counted on its own. A bot never trades Live, so Live's Bots line never moves.

2. **Whose trade.** A trade belongs to the side whose order opened its shares, read from the order's own stamps, never from its side, size or time: an order is the bots' when its source is `bot` or it carries a `bot_id` (the rule the Account page's by-source split uses), or when it is a bot's own close (sent as source `flatten` with the bot's origin: `bot`, `bot_api`, `live_trader`). Anything else is the operator's -- an approved plan, Nova's exit on the operator's shares, the operator's Flatten. Every Live fill is the operator's.
   - A fill first closes shares held the other way: its own side's first, then the other side's. Nova's own closes -- KILL, the day cover, a margin call, the Account line's Auto sell -- take from each side in proportion to what it holds. The cash a close moves and its share of the commission go to the side whose shares it closed. So the operator selling a bot's shares by hand, or Flatten closing them, counts on the Bots line.
   - The two sides always add up to the Account line's figure. A stock held before today still never counts, on any line.

3. **Each line acts on its own.** Each line has its own 80% warning and its own 10-second wait, and acts once per account and day.
   - **No new buys:** the Account line's trip refuses every new buy on the account, as before. The You line's refuses only the operator's (source other than `bot`); the Bots line's refuses only the bots' (source `bot`: every bot entry, Auto-entry and the Live Trader bot's steps). Selling, covering, cancels, Flatten, KILL and a bot's own exits are never refused.
   - **Auto sell:** the Account line sells every position opened today, as before (origin `loss_limit`). A side line cancels only that side's working orders on those stocks and sells only that side's shares opened today, with origin `loss_limit_you` or `loss_limit_bots`, so the count gives the sold shares back to that side and the Orders table and the voice name the line that sold. The Bots line's sale never goes to Live.
   - One sale per account per pass: when two lines trip in the same second, the second line's sale waits for the next pass and a fresh count, so no share is sold twice.

4. **Words.** Every notice, voice line and refusal names its line: "The bots' daily loss limit reached on Paper ... no new bot entries until 04:00 ET; your own buys still work."

5. **Migration.** The setting file goes to `schema_version` 2 (`you_usd`, `bots_usd`). A version 1 file reads as the Account line with its dollars and checkboxes unchanged and no You or Bots line, so nothing behaves differently until the operator sets one; the next save writes version 2. Today's record file goes to version 2 (one record per account and line); a version 1 record reads as that account's Account line, so a trip from before the upgrade still holds.

## Consequences

- A bot's losing day stops only the bots once a Bots line is set, and the operator can hold their own trading to a tighter line without stopping the bots.
- Mixed trades need the opening order's stamps; a practice order carries them in its ledger row (`order_source`, `bot_id`, `order_origin`). Rows Nova did not stamp read as the operator's.
- `GET /api/loss-limit` moves to `schema_version` 2: each account's warnings and trips sit under `lines`. The schema is `architecture/schema/loss-limit.md`.
