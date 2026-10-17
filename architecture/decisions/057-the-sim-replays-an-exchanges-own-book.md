# ADR 057 -- The Sim replays an exchange's own book, imported from a local file

**Status:** Accepted · **Date:** 2026-10-17
**Amends:** [[017-single-replay-surface]] (a historical window's depth gains a source, still on the one replay surface) · [[046-sim-replays-the-massive-flat-files]] (an imported venue book comes before the NBBO's one level)
**Asked by:** the operator, 2026-10-17: replay historical exchange depth in the Sim -- kept apart from the live desk, with its Sim replay integration as its own piece of work.

## Context

Level 2 on a replayed day comes only from Nova's own recordings: a Session Record's book (IBKR's depth lines, as the desk saw them) and the books `backend/l2/` archived (#309). The Massive flat files carry trades and the NBBO, never depth (ADR 046), so a day nobody recorded shows at most the best bid and ask as one level.

An exchange publishes its own order book, and its history can be kept as MBP-10 files: market by price, one record per change to the venue's book, each carrying the top ten levels a side after it. Databento's DBN encoding (an open specification) and its CSV form lay these out one venue's dataset at a time -- Nasdaq TotalView as `XNAS.ITCH`, NYSE Arca as `ARCX.PILLAR`. Nova could not read them.

Such a book is one venue's. Nasdaq's book holds only orders resting on Nasdaq: other venues' bids and offers are not in it, and neither is hidden or off-exchange liquidity, so its best bid and ask can differ from the national best quote. Drawn as "the" Level 2 it would mislead.

## Decision

1. **An offline import, by hand.** `py -3 tools/import_exchange_book.py import FILE --symbol XYZ --date YYYY-MM-DD` reads one local MBP-10 file -- DBN (versions 1-3) or the CSV form, plain, gzip, or zstd when the `zstandard` package is installed -- and writes that symbol-day's book into the Sim's exchange book store. It never touches the network, and nothing on the desk starts it: the desk only reads what it wrote. `list` and `remove` show and drop imported books.
2. **One venue per book, named on every row.** The venue comes from the file's dataset (DBN metadata; `--dataset` for a CSV, which names none): a table of single-venue datasets gives its code, as the tape names the venue (`NASDAQ`), and its desk name ("Nasdaq"). A dataset outside that table -- a consolidated one included -- a `--dataset` the file contradicts, a file mixing publishers, an MBO file and any schema but MBP-10 are refused with the reason, before anything is written. So are a symbol the file's metadata maps only on other dates -- an instrument id can belong to another security on another day -- and a damaged or cut-short file, a zstd one included (read frame by frame: zstandard's stream reader stops at a cut-short frame without a word). Every level the replay draws carries its venue (`mm`, `exchange`).
3. **The events as they were.** The importer keeps the symbol's records that end an exchange event (`F_LAST`: the book is whole only there) from 04:00 to 20:00 ET of the date, plus the last one before 04:00 -- the book standing when the day starts -- each with its ten levels a side (price, size, order count), the venue's flags, and the capture time (`ts_recv`) the file is ordered by. A time earlier than the one before it keeps its place in the file, takes the time before it, and is counted; nothing is re-sorted, resampled or filled in. A symbol-day-venue is one book: importing it again replaces it in one transaction, so it is whole or absent, and the old one plays until then.
4. **What a book covers is stated.** A book covers from the day's start (its first event, when the file starts later) to the file's own end (DBN `end`; a CSV's last event) or 20:00 ET, whichever is first. Inside that span the ladder at the playhead is the venue's last event at or before the playhead -- never after -- and a quiet stretch is a book that did not change. Outside it there is no venue book.
5. **Labelled on the desk, never the consolidated book.** The Sim's Level 2 reads "Nasdaq book only · last change HH:MM:SS ET"; a banner under it says what was imported and its span ("Imported · covers 04:00–20:00 ET · not the whole market"); each row names the venue in its market-maker column (where the pane is wide enough to show one); the header chip reads "Nasdaq book". Books of several venues imported for one day are drawn as one montage, each level keeping its venue, and named together ("Nasdaq + NYSE Arca books only"). A gap the venue flagged in its own feed (`F_MAYBE_BAD_BOOK`) is said over the ladder.
6. **First answer wins, at each playhead.** On a historical window -- an IBKR download or a Massive import -- depth is an imported venue book covering the playhead, else a book Nova recorded for that second (#309), else a Massive window's NBBO as one level (ADR 046), else none: the ladder stays empty with its stated absence. Where books were imported but none covers the playhead, the empty ladder says so and names the span they cover. A Session Record keeps its own recorded book.
7. **Shown, not traded.** The snapshot's `bid` / `ask`, practice fills, the SSR fill rule, the bot's depth-line rule, the Sim eyes, the sensors, the setup scanner and the charts read nothing from it. A venue's best bid is not the market's.
8. **Its own store, on the market data drive.** `<NOVA_MARKET_DATA_DIR>/sim/exchange_books.sqlite3`, beside the Massive imports, with its own `PRAGMA user_version = 1` (any other version is refused, never rewritten): one row per book, and its events in chunks of packed columns (2,048 events each, zlib), so a playhead inflates one chunk however long the day. Writes go through WAL, so the desk keeps reading while an import runs. A read never creates the store; an unreadable one is logged once and reads as no book.

## Consequences

- A past day with an imported book shows that venue's depth on the Sim ladder through its covered span, labelled as that venue's, beside the tape and the NBBO the replay already had. A day without one looks exactly as before.
- The import costs a by-hand command per symbol-day and venue; a busy day's file takes seconds to minutes to read, off the desk.
- Not built here: MBO files (a book rebuilt order by order); several files stitched into one book (an evening hour that sits in the next file is outside the book's span, and the banner says so); the venue book for the bot, the eyes or fills (decision 7); a listing or calendar mark on the desk for days with an imported book.

## Rejected alternatives

- **Merge the venues into one book labelled Level 2.** Even every venue together misses hidden and off-exchange liquidity, and the operator asked for exchange depth kept apart.
- **Keep the books in the Massive store.** Raising `replay.sqlite3`'s version would make an older desk refuse every Massive import (it refuses versions it does not know); a store of its own risks nothing that works today.
- **An import from the desk.** Reading a file of gigabytes is batch work, and ADR 046 already moved file reads out of the API process. A by-hand tool keeps the desk's loops free and opens no network path.
- **Resample to one book a second.** The file carries every change; a sample drops the changes inside each second and is still a choice made for the operator. Chunked columns hold every event in about the space a sample would take.
- **Fill an unimported moment from the NBBO or a nearby book.** Never: an absence stays an absence (ADR 019).

## How it was checked

- Backend tests on made-up XYZ files written in the published layouts: DBN versions 1, 2 and 3, the CSV form, gzip and zstd; another instrument in the same file, mid-event records, the book standing before 04:00, events after 20:00, a time that runs backwards, empty levels, the venue's bad-book flag; chunk edges, including a burst of events at one nanosecond across two chunks; never a book after the playhead; every refusal writing nothing; a second import replacing the first while the first stays readable until it commits; `remove`; an unknown store version; the snapshot's depth, coverage and precedence on an IBKR download and on a Massive window, with `bid` / `ask` untouched; two venues as one montage.
- After review (PR #1036): a mapping of other dates refused, a recycled instrument id refused under the wrong symbol and accepted under the day's own, gzip cut short or garbled and zstd cut short refused (each check fails on the code before it), a zstd file of several frames read whole, and the command's `--json` answering a damaged file as a refusal.
- Frontend tests: the ladder's venue note, coverage banner, venue on every row and header chip; the stated absence outside a book's span; two venues named together; the bad-book line; the payload parser.
