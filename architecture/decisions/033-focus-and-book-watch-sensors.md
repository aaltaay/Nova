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

## Amendment 2026-09-29: what left the book, on the ladder

**Decided by:** the operator ("I see massive orders in level 2, and I just think they're disappearing.
I don't see them on time and sales"; then "1 go" on putting the watcher on the ladder).

The watcher's verdicts reached only agents (the sensor) and the Trader's Tape tile, a number the
operator had to hover for, while the question comes up on the ladder. So:

1. **Every large drop is a verdict.** Besides its large pulls, the detector emits a `drop` event for
   each drop whose size -- traded or not -- passes the large rule (at least
   `BOOK_WATCH_LARGE_MIN_SHARES` and `BOOK_WATCH_LARGE_MEDIAN_MULT` x the side's median level), with
   its split and `outcome`. Showing only pulls would leave an unmarked vanished level ambiguous again:
   it traded, or it could not be judged.
2. **The depth socket carries them.** `book_watch/ladder.py` keeps each socket's place in its line's
   verdicts; the socket asks at most every `BOOK_WATCH_PUSH_SEC` (a verdict is ready
   `BOOK_WATCH_SETTLE_SEC` after the book that showed the drop, so a mark lands about a second after
   the size left). A new socket gets the last minute, so a price pulled before the Trader tab opened
   is still marked. One sender per socket: the book stream wakes on that clock instead of adding a
   second writer.
3. **The ladder draws facts, never intent.** A mark says where the size was, how much traded there
   and how much did not; a hatched row says big size was pulled at that price in the last minute
   and size sits there again. Amber and slate, never green or red (they mean bid and ask there);
   nothing covers a size or a price, nothing adds a row, and Time & Sales is unchanged. Every hover
   says "a hint consistent with spoofing, never a detection".
4. **No re-price filter.** On 2026-09-29's SSTI, MSGY and MEDS recordings, 1-5% of 205 large pulls
   had the same size reappear 1-3 ticks away within 0.5-5 s, so the pulls are not quotes stepping a
   tick. About a quarter came back at the same price within 2 s, which is what the hatching shows.

Live only. A replay desk's ladder is told the watcher reads only the live line; marking a recording
from the journal is parked (#617).

## Amendment 2026-09-30: hidden sellers and buyers

**Decided by:** the operator ("do we have a way to detect hidden sellers? like we have spoofing!?";
then the Level 2 mockup and "1 go": measure it on the Session Records first, then mark it on the
ladder and fix the flow sensor's `iceberg_hint`).

1. **The mirror of a pull.** A pull is size the book showed that left without trading; a hidden
   seller is size that traded at the offer beyond the most the book ever showed there.
   `book_watch/hidden.py` follows one **stretch** per side: the price its counted prints keep landing
   at (at or through the side's best price, and at that price after the size shown there is gone),
   weighed against the most the book showed there from `BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC` before
   its first print. It ends when a print goes through it, when its side's prints move the other way,
   after `BOOK_WATCH_HIDDEN_GAP_SEC` without a print there, at a cross print, or at a book reset.
2. **Not the prints no drop claimed.** The first design counted the prints the watcher's matching
   window could not tie to a fall in the size shown. On the recordings that called 60-75% of the lit
   volume at the quote hidden: the book and the tape arrive up to seconds apart, and a level refilled
   between two books never shows the fall. The most the book showed needs no timing.
3. **A hold, or it is a sweep.** Without one the rule fired mostly on sweeps -- a buyer taking the
   whole offer prints at a price and through it within milliseconds -- and 86% of the flags broke
   within 10 s, like the offers that showed their size. Measured with `tools/hidden_study.py` over
   the Session Records of 2026-09-21..29 (26 hours with a fresh book): with the price held 10 s,
   2,000 printed there and at least 3x the most shown, a minute after a hidden seller the mid was
   past the offer 37% of the time against 46% after an offer that took as much and showed its size
   (104 against 66; less often on 4 of the 5 days with both, a tie on the fifth), and the mid moved
   ~52 bp less toward the break (lower on all 5). A hidden buyer
   showed no such difference. Those are the defaults; the tool re-measures them. 64 rules were tried
   on few recordings, so the edge is a description of what happened, not a proven one.
4. **Which prints count.** Lit prints, odd lots included, only while the book is fresh (a book within
   `BOOK_WATCH_IDLE_SEC`): a Session Record can keep the tape after its depth line is gone (MSGY
   2026-09-29 09:41-09:56: 13,263 prints and no book, which a stale book called 683K shares hidden).
   Never: off-exchange (FINRA) reports, cross prints (`O 5 6 X Q M`; GRML reopened 2026-09-22 with one
   218,938-share print), volume-only prints. A midpoint print sits at neither side's price.
5. **On the ladder** (mockup v1): violet, never green or red (bid and ask), amber (pulled) or slate
   (traded). The row a hidden seller or buyer holds at is outlined and its mark sits under it
   ("◆ 12.4K hidden"); after it ends the mark says how ("· broke", "· held") and fades like a pull
   mark. Each side's minute line adds "◆". Every hover gives what traded against what showed, how
   it stands, the study's finding and "never a detection". The Trader's Tape tile reads "Hidden
   seller" while one holds at the offer.
6. **The sensors.** `/sensors/book-pulls` and its event feed carry the stretches' words;
   `/sensors/flow`'s `iceberg_hint` was true whenever any level grew while anything printed -- nearly
   always on a live name -- and is now the watcher's word (`null` without a depth line).
7. **Not decided here.** The setup scanner's tape gate keeps its own hidden-seller veto (one snapshot
   of the inside ask against the prints at the ask in 10 s). Replacing it with this rule changes what
   the bot enters on Paper and what the pre-registered read-out counts, on thin evidence: that is the
   operator's call.

## Amendment 2026-09-30: the matching window, measured

**Asked by:** the operator, after the hidden-seller study: the lit size at the quote that no drop
claimed often had a pulled drop at its price nearby (GCTK 2026-09-24: 34% shown 0.5-3 s before the
print, 25% 1-3 s after), so does the 0.5 s window (`BOOK_WATCH_MATCH_SLACK_SEC`) call fills "pulled"?
Change it "only if the evidence is clear".

1. **Measured against chance.** `tools/book_watch_window_study.py` (owner `book_watch/window_study.py`)
   runs the detector over the Session Records with its window at 0.5, 1, 2 and 3 s either side of a
   drop's two books, and weighs what a wider window adds against chance: the prints no drop claimed,
   against the same prints moved 30-60 s (to a moment their price stood in the same place against the
   quote) and moved one tick out, each moved print first meeting the drop's own 0.5 s window as an
   unclaimed one had. Cross prints and prints with no book within 5 s are left out. The detector takes
   the window as a parameter (`book_watch/matching.py`); the live watcher runs the defaults.
2. **The evidence was chance.** A busy price always has a pulled drop near a print. Over the 27
   recordings of 2026-09-21..29, the same prints moved 30-60 s had a pulled drop shown 0.5-3 s before
   them as often (45.3% of the size against 44.9%), and one shown 1-3 s after them more often.
3. **The book does trail the tape, a little.** Of 339,550 lit prints through the displayed best price
   -- proof that the best level traded -- 87.9% saw a book show that level gone within 0.5 s and 10.2%
   took 0.5-3 s. Those levels read as pulled.
4. **A wider window claims them, and more by chance.** Reaching 1 s before the earlier book would fill
   2.3% of the 82.0M shares the 0.5 s window calls pulled, only 0.5-0.6 points of it beyond chance;
   3 s, 7.8% with 1.3-2.2 beyond. Reaching past the later book, 2.0% at 1 s with 0.2-0.3 beyond. At
   1 s either side the large pulls would fall from 11,121 to 10,707 and the flags from 3,190 to 3,132,
   mostly on claims chance explains, and a longer reach past the later book delays every ladder mark by
   as much.
5. **So the window stays 0.5 s either side.** For each fill it would recover, a wider window makes
   about three to five chance claims before the earlier book and six or more past the later one.
6. **Exact prices.** A lit print fills only a level at exactly its price. The old half-tick test let
   floating-point error match a midpoint print (3.655) to the level below it: 0.2% of the dropped size
   moves from filled to pulled, 15 more large pulls of about 11,000, no flag.
7. **Parked (#636), then built** (next amendment). A print through a displayed level proves that level
   traded. Holding the level's next drop as traded for a few seconds would mend the late book without
   claiming chance prints; 421 of 11,310 large pulls (3.7%) were such levels.

## Amendment 2026-09-30: a level a print traded through reads traded (#636)

**Decided by:** the operator ("1 go" on building #636 after the matching-window study).

1. **The proof.** A lit, price-setting print above the book's best ask (below its best bid) proves the
   size the book showed at the round-lot levels from the best to its own price traded: a protected
   quote cannot be traded through. IBKR's book can show that size for seconds more, and its drop then
   reads pulled. The matching-window study's 10.2% of through-prints shown gone only 0.5-3 s later mixes
   two things, which its depth-late measure now tells apart (`grew_first`): a level the book left
   untouched until then (the book trailing its tape) and a level the book showed new size at first (a
   refill). Of the 339,550 through-prints, 12.1% were not shown smaller within 0.5 s: for 4.2 points of
   them the book showed new size at the level first, and 7.8% sat in the book untouched until it showed
   them smaller (or for 10 s). Counting only the prints the rule takes as proof (87,430: no odd lots,
   crosses or volume-only prints) gives the same split -- 88.0% shown within 0.5 s, 4.5 points refilled
   first.
2. **The rule** (`matching.Sweeps`). A sweep leaves the size the book showed at each level it took owed
   there. For `BOOK_WATCH_SWEEP_HOLD_SEC` (3 s) after it, a drop at one of those levels first takes the
   sweep's own prints -- the lit prints at its exact price within 0.5 s of the sweep -- at most the size
   still owed, then its own window; every drop the book shows there pays the owed size down. New size
   posted at the level, or the level leaving the view, ends it. Only real prints at its price: a level
   pulled before the sweep reached it has none there and still reads pulled. A print proves nothing when
   it is an odd lot, a cross, a volume-only or an off-exchange print, when the best it went through is
   an odd lot (`BOOK_WATCH_SWEEP_MIN_LEVEL`: not a protected quote), or when the book is older than
   `BOOK_WATCH_IDLE_SEC`. A book reset forgets every sweep.
3. **What the first build got wrong.** It let any drop at a swept level within the hold take the sweep's
   prints, with no limit and through refills. The placebos passed it -- 77.5% beyond chance against the
   same sweeps moved, 83.9% against a tick past -- because the prints it claimed were real and near a
   real sweep; the drop they filled was the error. Read against the book: on six busy recordings 84% of
   the size it relabeled sat at a level the book had shown new size at since the sweep. On BKYI
   2026-09-29 the 3.40 bid showed 551 when prints went through it, and 10,142 printed there within 0.5 s
   of them (a hidden buyer). The book showed the 551 gone 0.2 s later; then a new bid appeared, grew to
   10,300, and 5,600 of it left the book 2.3 s after the sweep with 1,185 printed near it. The first
   build read all 5,600 traded, from the sweep's leftover prints. The owed size and the end on new size
   remove that; what is left is the size the sweep proved. Letting a drop take every print since the
   sweep, not only the sweep's own, was dropped earlier for the same reason: it claimed refills.
4. **Measured** (`tools/book_watch_window_study.py`, section 5; `book_watch/sweep_study.py`) on the 27
   recordings of 2026-09-21..29, through the detector itself -- its own sweeps off and the study's
   placed in the same code for the placebos. 9,695 sweeps; the drops the rule covers (12.1M shares) read
   86.2% traded without it and 88.7% with it. It adds 299,598 shares, 0.37% of the 82.0M the watcher
   called pulled. Against the level a tick past each sweep, 97.7% of that is beyond chance; against the
   same sweeps moved 30-60 s, 76.4%, on the fifth of the gain whose sweeps could be moved. The recordings
   that kept every book IBKR sent (2026-09-25 and -29, as the live watcher sees it) show less: 0.14% of
   the pulled size, 91% and 49% beyond chance; recordings before 2026-09-24 09:21 ET kept at most 8 books
   a second. Large pulls 11,121 -> 11,071, flags 3,190 -> 3,176, large drops traded 28.4% -> 28.8%.
   Small, because most of the first build's 1.6% was the wrong drop.
5. **The window still stays 0.5 s.** With the rule on, a window reaching 1 s before the earlier book
   would still add 2.0% of the pulled size, 0.3-0.4 points of it beyond chance (2.3% and 0.5-0.6 without
   the rule). What stays wrongly pulled is size that traded at the best with nothing through it, shown
   gone late, and size swapped at a level within one book update (the swept size gone and as much
   posted, so the book shows no change): nothing on the tape or the book proves either. Prints are
   matched by price, not venue, so a venue's order cancelled just before the sweep reached it can take
   a hidden order's print at that price, up to the size shown.
