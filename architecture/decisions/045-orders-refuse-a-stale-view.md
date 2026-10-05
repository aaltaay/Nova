# ADR 045 -- Orders refuse a stale view; the market path stays real time

**Status:** Accepted · **Date:** 2026-10-05
**Amends:** [[007-centralized-trading-execution]] (a desk order carries the view it was priced from; the door refuses a stale one) · [[010-ib-loop-isolation]] (the IB thread hands market data to the socket loop through thread-safe, coalesced wake-ups) · [[026-performance-recorder]] (freeze dumps, page faults, per-generation GC pauses)
**Decided by:** the operator, 2026-10-05, after an APUS sell rested above the market:
- "Why the fuck has our order not kicked in yet? ... It crossed that number for sure. We are trading at 640-something. This should never happen."
- "I don't want you to just create a new script ... I need this to be a part of the code. This lag should never exist ever. If level two determine sell, I don't need it to say n seconds behind. If it lags, then we cannot place an order."
- "Everything needs to happen in real time ... This is about reliability."

## Context

At 08:30:25 ET the operator sold 100 APUS at what their Level 2 showed as the bid: DRCTEDGE 400 @ 6.58. That book was Nova's own from 08:30:18-21; at the click Nova's book was 6.50 x 6.55 and Time & Sales showed 08:30:20 as its newest print. The order reached the backend 2-3 s after the click (the HTTP loop was stalled), arrived above the market and rested on Paper; it filled at 6.58 at 08:31:21, on off-exchange prints made during an 8.8 s freeze of the whole backend (08:31:07-16), after which the price fell to 6.26. Measured that day:

1. **Level 2 and Time & Sales were queues, not views.** Each viewer had a FIFO (100 books, 2048 prints) filled from the IB thread with `asyncio.Queue.put_nowait`: not thread-safe, and it never wakes the socket's loop, so a frame waited for some other wake-up. After any stall the socket replayed up to 100 old books in order. A full book was queued on every L1 tick and print of the symbol (one shared ib_async Ticker), changed or not. No frame carried a time.
2. **The socket loop blocked.** The same loop serves Level 2, Time & Sales, quotes and orders. It stalled 1,047 times (536 s) on a `tasklist` subprocess asking whether IB Gateway runs -- which also answered "no" while the Gateway ran as `java.exe` under IBC -- and on `cache_dir()` creating its folder on every call (about 25 per order), the order overlay re-read on every 5 s poll (1-4 s), and the IBC log re-read on every status poll.
3. **The whole process stopped.** 49 times since 05:00 the perf sampler itself missed 2-11 s; in the busy 08:15-08:35 window garbage collection took 1-2.7 s of every 5-7 s; the 08:31 freeze kept one core busy and left no stack.
4. **The trading path ran below background work.** The backend and IB Gateway ran at BelowNormal (inherited from a scheduled task, kept across every restart) while builds, browsers and agents ran at Normal.
5. **Nothing measured how old the operator's view was.** The ticket priced from it, and the door accepted any order.

## Decision

1. **The order gate is the authority.** A desk order (`POST /api/ibkr/order`, `PATCH /api/ibkr/order/{id}`) carries `view`: when the operator acted, and the Level 2 book and the quote the screen showed (each by its sequence number). The execution door refuses a manual place, bracket or replace, before anything is sent:
   - `VIEW_STALE`: what the screen showed had been replaced by a newer book or quote for more than `ORDER_VIEW_MAX_LAG_MS` (500) at the action, judged by the backend from its own version history; or the frames came from a backend process that has since restarted.
   - `ORDER_LATE`: the order reached the door more than `ORDER_MAX_ARRIVAL_MS` (500) after the action, or the broker send more than `ORDER_MAX_SEND_MS` (750) after it.
   - `FEED_STALE`: Nova itself is behind the market: an IBKR feed gap is open or settling, or the IB loop is stalled now for more than `ORDER_MAX_IB_STALL_MS` (500). Not on a Sim desk off the live edge: its orders fill against the replay, whose health IBKR's feed does not describe.
   - `VIEW_MISSING`: a desk order without `view` (an older desk).
   Flatten (the protective sources), KILL, cancels and Nova's own senders (the bot, stock modes, the breakers) are never refused by it: they do not price from the operator's screen, and getting flat must always work. The gate uses the desk's and the backend's wall clocks together, which is sound only because the backend binds 127.0.0.1: one machine, one clock. Every gated order records its `view` and the gate's measures.
2. **The desk locks first.** While a Trader tab's Level 2 is behind -- no word from the backend for `VIEW_SILENT_LOCK_MS` (750; the backend speaks every 250 ms), a frame that took more than 500 ms to arrive, or a book received and not drawn for more than 500 ms -- Place, the quick bar, the hotkeys and Fill now are locked, each saying why. There is no "N s behind" readout: the controls are locked or live.
3. **Level 2 is the newest book, never a backlog.** Each viewer holds one slot with the newest book and a short FIFO for its control frames (`error`, `lent`), filled from any thread; the producer wakes the socket's loop once (`call_soon_threadsafe`, coalesced). A book is pushed only when it changed. Every book frame carries `seq` (per symbol, +1 per change), `at` (when Nova applied it) and `sent`; with nothing new for `MARKET_VIEW_BEAT_SEC` (0.25) the socket sends `beat` `{seq, at, now}`. `subscribed` names the backend `instance`.
4. **Time & Sales arrives whole and in order.** Each viewer's prints sit in a thread-safe FIFO (2048, oldest dropped and counted) with the same coalesced wake; the socket sends everything waiting as one `prints` frame (a single print stays a `print` frame).
5. **The quote stream is versioned.** `trade_update` frames carry the symbol's quote `seq` and `at`, so the gate can judge a view without Level 2.
6. **Nothing slow on the socket loop** (this change): the Gateway check reads Windows' process list and listening ports in-process, with no subprocess, and finds the Gateway's `java.exe`; `cache_dir()` and `log_dir()` create their folder once; the order overlay is cached until the ledger changes; the IBC log is re-read only when it changed; the gateway trail likewise; a Time & Sales subscribe warms its 10-second bars off the loop.
7. **The trading path runs above background work.** The backend raises itself to Above Normal and opts out of Windows power throttling at start and every 2 s (other software on the desk PC lowered it after it started), raises its two loop threads, keeps IB Gateway's process at Above Normal and IBC's launch loop, whose relaunch the Gateway inherits, at Normal; the desk's Electron main raises its own and its desk windows' processes. Nothing is ever lowered, and a priority found lowered is raised and logged. The checklist row `process_priority` says what each runs at.
8. **A freeze names itself.** A C-level watchdog (`faulthandler`) dumps every thread's stack when the process stops for `PERF_FREEZE_DUMP_SEC` (2); the dumps are kept under `<cache>/perf/freezes/` and the checklist row `perf_freezes` names the last. Perf samples add page faults, the working set and GC pauses per generation.

## Consequences

- An order priced from a view that lags is refused with the reason, and the desk locks before the click while it can see the lag. The incident cannot recur silently: at worst the order is refused and says why.
- A busy name sends fewer Level 2 frames (changes only), and the desk always draws the newest book.
- Thresholds are constants, set from this incident; every order records its measures, so they can be tightened with evidence.
- Deferred, each to be judged by what the stamps measure after this change: a separate real-time server for the market sockets and orders (it moves every socket handler across event loops; #726); Live's order send waiting on IBKR while holding the socket loop (`call_on_ib`; #725); moving HOD Momo's per-tick evaluation off the IB thread (36 ms/s that morning) and GC threshold tuning (per-generation pauses are recorded first), both with #619.
