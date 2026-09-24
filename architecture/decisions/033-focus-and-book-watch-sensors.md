# ADR 033 -- Sensors for agents: the operator's focus and the book watcher

**Status:** Accepted · **Date:** 2026-09-24
**Builds on:** [[026-performance-recorder]] (window reports) · [[010-ib-loop-isolation]] (enqueue only) · `architecture/capture-fidelity.md` (L2 coalescing)
**Decided by:** the operator, 2026-09-24 ("when I have a fast question, you can answer me"; "do we have
sensor endpoints? ... when we develop testing strategies, our bots have more things to rely on";
"if your recommendation is only to do 1, 3, 9, and 10, let's do them")

## Context

Asked "which ticker am I focused on?" and "can you read Level 2 fast and check for spoofing?", an agent
had to guess. Nova told the backend which Trader tabs held Level 2 (`/api/bot/focus` `trader_live`) but
not which tab was active, which page or window was in front, which monitor it sat on, or when the
operator last touched it. The Level 2 sensor's "spoof hints" diffed books keyed by price alone, so the
venue rows at one price overwrote each other, and it never looked at the tape, so a level that traded
away read the same as one that was pulled. And the Session Record kept at most 8 books a second: on
2026-09-24 it held back 63% of GCTK's books and 76% of PFSA's, while the manifest's `l2_coalesced`
read 0 because the books were thinned before the counter saw them.

## Decision

1. **Focus is reported, never guessed.** Every desk window posts its focus report to `POST
   /sensors/focus` on each change (Windows focus, visibility, page, symbol, the operator's first
   input after a pause) and every `FOCUS_HEARTBEAT_MS`: the page, the scanner tab, the symbol the page
   is on and where it came from, and when the operator last clicked or typed there. The Electron main
   process posts which Nova window has Windows focus and the monitor each window is on (only it can
   know). `GET /sensors/focus` joins them into one answer. Where the operator's eyes are cannot be
   known; Windows focus plus the last input is the stated stand-in. In memory only, never persisted.
2. **The book watcher** (`backend/book_watch/`) follows every held depth line with the tape, off the
   IB loop: the IBKR depth and AllLast callbacks only enqueue; one thread aggregates each book by price
   across venues, compares only the prices fully visible in both books (a price at the edge of the ten
   rows may be cut off, and a price that scrolled out of view is unknown, never "pulled"), and splits
   every drop in resting size into **filled** (lit prints at that price in the matching window) and
   **pulled** (the rest). It flags large pulls, pulls as the price came toward the size, and repeats
   -- each with its evidence -- as **hints consistent with spoofing, never a detection**: the feed has
   no order ids and no owners, IBKR batches depth, and every time is Nova's arrival time.
   `GET /sensors/book-pulls` reads it; flags and one summary per symbol-minute go to a journal for
   bots and backtests; `tools/book_watch_replay.py` runs the same detector over a Session Record.
3. **The recording keeps every book IBKR sends** (up to `CAPTURE_L2_MAX_HZ`, raised from 8 to 50 as
   a flood bound), batched to the writer like prints, and `l2_coalesced` counts every book held back
   anywhere, so the manifest says what it lost.

## Consequences

- An agent answers "what am I looking at?" from `GET /sensors/focus`, and "is anyone pulling size?"
  from `GET /sensors/book-pulls` -- the same answers a bot can read.
- Recordings of busy names grow: at IBKR's rate GCTK's Level 2 is about 2.7x the 8 Hz file and PFSA's
  about 4x, still smaller than their prints.
- The watcher sees only the symbols Nova holds depth for (at most 3) and ten rows a side. More lines,
  more rows or order-by-order data are IBKR account or paid-feed questions, not decided here.
- Nothing here places, gates or cancels an order.
