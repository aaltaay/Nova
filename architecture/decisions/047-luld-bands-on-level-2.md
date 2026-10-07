# ADR 047 -- LULD bands on Level 2: Nova's calculation from the published rules, measured against the SIP's

**Status:** Accepted · **Date:** 2026-10-06
**Amends:** [[033-focus-and-book-watch-sensors]] (the depth socket carries a third kind of frame) · [[036-the-bots-read-on-one-stock]] (the stock read's "Limit up / down band" row is computed, no longer "Not computed")
**Decided by:** the operator, 2026-10-06: "do we have LULD levels?", then, with DAS Level 2 screenshots of red `LULD` rows at each band: "1 go.. make it obvious, show me the results after you are done".

## Context

A stock that stays on a Limit Up-Limit Down band for 15 seconds is paused for five minutes, and a trader long into a pause on the way down cannot get out until it reopens. DAS draws each band as a red `LULD` row in its Level 2 montage, from the SIP's price-band messages. Nova had the halt (IBKR's tick 49, the Nasdaq halt feed) and a reopen countdown, but no band: the IBKR API passes on no band field, and the Nasdaq halt feed's pause-threshold price was blank in all 43,420 archived pauses. A prototype of 2026-09-29 replayed the published rules over four recorded pauses: 1 exact, 2c, 4c and 36c off.

## Decision

1. **Nova computes the bands** from the LULD Plan's rules (Amendment 20, Sections V-VII and Appendix A; the Nasdaq LULD FAQ), applied to the tape and NBBO it already holds (`backend/luld/`):
   - The percentage comes from the previous close on the listing exchange, fixed for the day (IBKR's tick 9, split-adjusted). Over $3.00 it is 5% (Tier 1) or 10% (Tier 2); from $0.75 to $3.00, 20%; under $0.75, the lesser of $0.15 or 75%. From 15:35 to 16:00 it doubles for Tier 1 and for Tier 2 at or under $3.00. Bands round to the penny, half up.
   - The first reference is the listing exchange's opening print. For five minutes after it, the mean of the trades since; then the mean of the eligible trades of the last five minutes. A new mean replaces the reference only when it moves 1% or more, and only after the old one has stood 30 seconds. A limit state holds the reference. A reopening print is the next reference.
   - "Eligible" is Nova's rule for a print that sets a price (`sale_conditions.py`, the Plan's "eligible to update the last sale price").
2. **Where the Plan leaves room, the SIP's own data decides.** The Massive NBBO rows carry the SIP's LULD indicators. Every row where the SIP flagged the bid on the upper band, or the offer on the lower, gives the band's exact price, so the rules were measured against the exchanges' own bands rather than read alone (`luld/study.py`, `tools/luld_check.py`). Two readings came out of it:
   - **No reference at a limit state's end.** The Plan's text says the reference becomes the five-minute mean the moment a limit state ends (Section VI(B)(4)). The SIP's flags say it does not: matching that text scores 64% exact, keeping the reference in force scores 81%.
   - **The mean unrounded.** Rounding the reference to the cent scores 54%; to four decimals, the same as unrounded.
   - **Checked continuously.** Checking the reference only when a trade prints scores 80% exact against 81%, with slightly more touches within a cent (89% against 87%). The two differ on few touches, and neither explains the rest.
3. **Exact or approximate, and said so.** A band is `exact` when Nova saw the stock open or reopen, with its tape unbroken since: the published rules, applied. A stock first watched mid-session gets a band only after five minutes of tape, seeded from the mean and marked `≈` with how far it may sit from the exchanges'. A lost line or an IBKR feed gap makes an exact band approximate until the next reopen. An approximate band never claims a limit state.
4. **The tier is Nova's reading, and says so.** Nova keeps no S&P 500 / Russell 1000 list, and the tier matters only over $3.00. A company of at least $15B is Tier 1 and one of at most $2B is Tier 2, both sure. Between them, or with no size known, Nova takes the likelier tier (Tier 2 with no size: nearly every stock that halts is) and marks the band `≈` with the reason.
5. **On the ladder, as DAS draws it.** The depth socket sends `{"type": "luld", "data": view}` when the view changes, and every 5 seconds otherwise. The Level 2 ladder draws the lower band in the bid column and the upper in the ask column, each a bold rose line with a `LULD 4.40` tag where its price sits among the rows, or under the last row (`↓`) when deeper. A 15 px strip above the book shows both bands with their distance from the last trade, amber near one. In a limit state it turns red and counts the 15 seconds down to the pause. Off-hours the strip takes no room. Every piece's hover says it is Nova's calculation, how it knows, and the measured track record.
6. **Live and replayed.** The live worker (`luld/live.py`) follows every stock whose AllLast line Nova holds. The IBKR callbacks only enqueue (ADR 010), and one thread keeps the trackers. On a Sim desk off the live edge with a Session Record loaded, the ladder shows the bands at the playhead from the recording (`luld/replay.py`, a worker thread with checkpoints, never ahead of the playhead).
7. **Read-only.** Nothing here places, stages, gates or cancels an order. The halt chip and its reopen countdown are unchanged.

## How it was checked

- **The SIP's own bands (Massive, 2026-09-21..10-05).** 10 trading days; the stocks the Nasdaq halt log paused; one comparison per touch (a run of NBBO rows the SIP flagged at one band price).
  - Headline: 166 ticker-days under $50 with a trustworthy previous close, 593 touches with an exact band. Nova's band matched to the cent on 480 (80.9%), within 1c on 513 (86.5%), within 5c on 551 (92.9%).
  - Approximate bands (a tracker started 30 minutes after the open, before any reopen) were within their stated spread on 126 of 152 touches.
  - Set apart: a previous close far from the day's first trade (a split the day aggregates do not adjust), and names over $50 (Tier 1's 5% bands; the study assumes Tier 2).
- **Nova's own Session Records (IBKR's data, the live desk's).** The three GRML pauses of 2026-09-22 on tape (09:36:33, 10:50:36, 10:56:47) land exactly on the pinned price: 14.18, 17.18, 15.87. The limit state was seen 13-15 s before each pause.
- 60-odd backend tests for the rules, the state machine, the worker, the socket frames, the replay and the study reader, and desk tests for the rows, the strip, the countdown and the frames.

## Consequences

- The operator sees the halt line before the stock reaches it, and the 15 seconds when it does.
- About one band in five is off by a cent or more where the SIP's own flags could check it, mostly by 1-3c. The cause is not known yet: the SIP's exact moment of re-evaluation, or which trades it counts. The track record is quoted beside the line, never hidden.
- A stock first opened mid-session shows an approximate band for the rest of the session, or until it halts and reopens. Seeding it exactly from IBKR's historical ticks is not built.
- Re-measure with `py -3 tools/luld_check.py massive` after a change to `luld/tracker.py`, and update `luld/track_record.py`.
