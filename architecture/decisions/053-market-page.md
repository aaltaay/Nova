# ADR 053 -- The Market page: the day's market health at a glance, in place of the Desk

**Status:** Accepted · **Date:** 2026-10-13
**Builds on:** [[040-cryptos-page]] (a read-only reference board: wanted window, background refreshers, stated
absences) · [[012-local-first-chart-bars]] (the paced historical service) · [[023-scanner-leaderboard]] (the
leaderboard store) · [[010-ib-loop-isolation]] · [[005-frontend-feature-slices]]
**Decided by:** the operator, 2026-10-12 and 2026-10-13 ("The Desk is like being copied from the Trader, we don't
want it ... i want overall dashboard of the market. showing futures / which sectors are up and which ones are down
... identify the overall health of the market for the day in one glimpse and show the top stocks for each sector";
mockups v1-v5 iterated as PNGs; picks: a verdict with its checks, worded Bullish / Mixed / Bearish; ranked sector
bars; the Market page replaces the Desk; real futures; every block its own 1 D / 7 D / 30 D switch, remembered;
"i'm ready for you to implement the dashboard, go!"). The operator subscribed IBKR's CME, CBOT, NYMEX and COMEX
Real-Time (NP, L1) and Cboe Streaming Market Indexes on 2026-10-13 for it.

## Context

The Desk page (the Scanner + Trader hybrid of the approved UX redesign, #429) duplicated the Trader beside a condensed
board. The operator wants instead one read-only page that answers "how healthy is the market today?" before and
during the 07:00-10:00 trading window: the futures, the fear gauge, which sectors and industries lead and lag, how
many stocks join the move, and -- for a small-cap momentum trader -- how hot the small-cap tape is, by day, week and
month.

Nova had no futures, index or breadth quote (every IBKR contract was a `Stock`), no sector membership and no
economic calendar. IBKR error 10089 ("requires an additional subscription") from any request set a session flag
that switched the whole connection to delayed data, so one unsubscribed reference symbol could have moved the stock
desk to delayed quotes.

## Decision

1. **A `Market` page takes the Desk's place, first on the nav rail** (`frontend/src/market_board/`, backend
   `backend/market_board/`). The Desk page, its board and its sample are removed; the HOD Momo dock stays on the
   Scanner. Read-only: nothing on the page places, stages or cancels an order, and nothing on it feeds a scanner
   row, a chart, HOD Momo, a setup lane or a bot. A stock symbol opens the Trader.
2. **Every price is IBKR's.** Futures (the front month of ES, NQ, RTY on CME, YM on CBOT, CL on NYMEX, GC on COMEX,
   found through IBKR's continuous-future definition and re-resolved at each roll), Cboe indexes (VIX, TNX), NYSE's
   market indicators (AD-NYSE, VOL-NYSE, TICK-NYSE, TRIN-NYSE), Bitcoin (IBKR's Zero Hash quote), sector and industry
   ETFs and stocks, all through cold, droppable snapshots (`ibkr.ib_scheduler.cold_slot`; since the 2026-10-13
   amendment below, a line held for a moment instead), and intraday / daily bars
   through the paced historical service at background priority. Every quote carries IBKR's own market-data type
   (live, delayed, frozen), and the page says "delayed" when IBKR says so. A symbol IBKR refuses says why on its own
   tile; no other source stands in.
3. **The board's requests never touch the stock session's flags.** An IBKR error on a future, index, forex or
   crypto contract is recorded for that tile and returns before the session error hook can set the delayed-data
   fallback, the max-tickers note or a farm notice (`ibkr/session_errors.py`). Stocks are unchanged.
4. **The page never holds a market-data line** (amended 2026-10-13, below: it holds one only for a moment). It streams nothing: snapshots run only while at least
   `MARKET_MIN_FREE_LINES` of the account's lines are free, a few at a time, and yield to interactive work. Its reads
   run only while the page asked within `MARKET_WANTED_SEC`, except the NYSE breadth sampler, which takes one
   snapshot of the four indicators a minute during the regular session so the day's up-minus-down line exists when
   the page opens. `NOVA_MARKET_BOARD=0` turns every refresher off.
5. **Reference facts that are not prices come from named public files, labelled:** State Street's daily SPDR
   holdings files (sector membership and each sector's biggest names); the BLS and BEA release calendars; the
   Federal Reserve's FOMC meeting dates and SIFMA's bond-market holidays (constants copied from their published
   calendars, with the source URL); earnings from Nova's existing Finnhub calendar; a stock's industry from IBKR's
   own contract details. A file that fails says so; its rows read unknown.
6. **The small-cap climate is Nova's own record.** It reads the leaderboard store (ADR 023) through one lens --
   the recorded Gainers board's first `MARKET_CLIMATE_RANK_MAX` ranks at or above `SCANNER_MIN_PRICE` -- and says
   how many of the period's sessions Nova recorded. Rebuilt days are left out: they rank every listed stock's
   minute bars, not IBKR's scan, and counted about 40% more runners a session (61 against 42 over the weeks either
   side of 2026-09-23), so mixing them would call every recorded week cold. A runner is a stock whose change from
   the prior close reached the threshold that day; halts are the Nasdaq halt feed's starts.
7. **The day read is a stated rule, not a model.** Six checks (futures, breadth, VIX, small caps vs large caps,
   runners vs their average, gappers holding their open), each green, red or waiting with its number; the verdict is
   Bullish, Mixed or Bearish by `MARKET_DAY_READ_*` thresholds over the checks that have data. Before 09:30 the
   checks that need the open say when they start.
8. **Each block keeps its own 1 D / 7 D / 30 D switch** (Sectors, Industries, Top stocks, Small-cap climate),
   remembered on the desk across restarts. The day read, futures and breadth are today's by nature. 7 D is the
   last five sessions, 30 D the last 21.

## Consequences

- The page costs IBKR snapshots and paced historical requests while it is open; it costs nothing while it is not,
  apart from four breadth snapshots a minute in the regular session.
- A subscription that has not reached IB Gateway yet shows as "not subscribed" on its tile until the Gateway's next
  login.
- Stated absences in v1: Nasdaq breadth and new highs / lows (IBKR's API documents neither), the up / down split of
  halts (the halt log does not store the side), leaders for theme ETFs with no member file (QTUM, BOTZ, URA, WGMI,
  KWEB, JETS, TAN, MSOS, GDX, SMH, IGV), intraday lines for the top-stock rows (shown for 7 D and 30 D from daily
  closes), relative volume.
- The runner counts are the Gainers board's, premarket included, so they read higher than a regular-hours-only count.

Rejected: Yahoo / third-party quote APIs (unofficial or delayed, and a second price source); computing VIX from option
quotes (hundreds of lines, and an estimate posing as the index); streaming lines for the page (they would compete with
the scanner and HOD for the account's 100); classifying runners with yfinance (a network call per symbol, rate
limited); a model writing the verdict.

## Amendment 2026-10-13: a line held for a moment, and bars that never wait behind quotes

The operator, at 13:29 ET with the page open: "everything is frozen, data is so so so slow. has this never been
measured?" It had not been. The perf record (ADR 026) timed the IB loop and `ibkr.snapshot_quotes`; nothing timed
the Market page's own reads or how long the page takes to fill.

Measured that afternoon on the desk, 14 minutes after a backend start: the futures were 132 s old, VIX and TNX had
no price, no tile had a line, no sector or industry had a move, and Top stocks said "the sector ETFs have not been
quoted yet". Polling the page for three minutes, one pass of the nine tiles took 23 s, 39 s and 66 s, the futures
refreshed about once a minute against a 10 s target, the 28 ETFs took 20 s, and not one tile line or VIX / TNX price
was read. Two causes:

1. **A snapshot waits for IBKR's snapshot end.** For a future, an index or NYSE's indicators that is about 11 s a
   batch at any hour, because some of the fields it waits for never come. For stocks it is the same outside the
   regular session: `ibkr.snapshot_quotes` took a median of 11-12 s in every hour from 00:00 to 09:00 ET on
   2026-10-12 and 10-13, and 1.4 s in the session. Nine tiles in batches of two were five such waits.
2. **Every IBKR read ran on one thread, first due first.** The tiles are due every 10 s and took 23-66 s, so the bar
   reads below them never had a turn: each tile's line, VIX's and TNX's price (their snapshots carry none), the
   ETFs' daily closes. A bar read takes about a second.

So decision 4 now reads: **the page holds a market-data line only for a moment.** It reads a quote by opening at most
`MARKET_STREAM_BATCH` lines (5, as many as a stock snapshot holds), taking IBKR's first ticks (a price and the prior
close) and cancelling the lines at most `MARKET_STREAM_WAIT_SEC` later. A snapshot held the same lines for up to
11 s, so the page's peak is unchanged and its line-time falls. As before, it opens nothing with fewer than
`MARKET_MIN_FREE_LINES` spare and keeps no line between reads. It no longer queues in the cold snapshot slot
(`ib_scheduler.cold_slot`) behind HOD Momo's and discovery's snapshots: a brief line is not a snapshot. It never cancels a line someone else holds: a contract the desk already streams is read from that line, and one the
desk subscribes during the read is left open for the desk.

Bar reads get their own thread, `history`: the tiles' prior closes and lines, the ETFs' and leaders' daily closes,
the bar prices when no line is spare, and runners' industries. Each tile's prior close and line are read together,
tiles without a price first. The `ibkr` thread keeps breadth, the quotes, the ETFs and the movers scan.

Every read's time now goes into the perf record as `market_board.<read>` (wall time), and the time from the page
opening to each read's first answer as `market_board.first.<read>`.

Rejected: one batch of nine snapshots (still an 11 s wait each pass, with nine lines held for it); holding lines for
as long as the page is open (the rejection above stands: they would compete with HOD Momo for the 45 lines Nova could
hold on 2026-10-13).

Later the same day the line held for a moment became shared (ADR 054): `ibkr/brief_lines.py`, its constants
`IBKR_BRIEF_LINE_*` and `IBKR_BRIEF_MIN_FREE_LINES` (were `MARKET_STREAM_*` and `MARKET_MIN_FREE_LINES`, same
values). An ETF or a stock is now priced by its last trade, never by a quote that arrived first, and its line asks
the desk's generic ticks.

## Amendment 2026-10-13 (evening): the page is ready before it opens, and no block is left empty

The operator at 17:38 ET, with the page on screen: "i see lots of issues here.. empty widgets, the symbols are not
clickable.. and the runners per session is so tiny no hover, no maximizing.. i just feel like its half ass done",
then "this need to load while all other items in this app need to run, dedicated worker/process ... this need to be
very efficient, and when you close, it's pretty slow to load ... Shower it with tests."

Measured on the desk that evening (the perf record, ADR 026, and `GET /api/market/board`):

- **The slow open.** `market_board.first.closes` was 509-632 s: the 7 D / 30 D moves, the top-stock lines and the
  period leaders reached the page 8½ to 10½ minutes after it opened. About 105 daily-close reads queue one at a time,
  2 s apart, on the `history` thread, run only while the page asks, and start over in every new backend process.
  The desk app's backend restarts when the app is closed and after every update.
- **The empty futures.** From 17:00 to 18:00 ET CME pauses trading every day, so a brief line gets no trade. The bar
  fallback dropped any bar older than `MARKET_BARS_FRESH_SEC`, so ES, NQ, RTY, YM, CL, GC and the small-caps tile
  read "--" while their lines were drawn.
- **The squashed lines.** Each tile's line was drawn on a 04:00-16:00 axis, so every point after 16:00 piled up
  at the right edge. Bitcoin's line also started at 16:00 ET, because IBKR's "1 D" of crypto bars starts there.
- **Breadth after the close.** The card lost up / down volume and TRIN. The day's samples keep only the counts
  and TICK, and after the close the last sample stood in for the day.
- **Empty top-stock cards.** A sector with no stock in IBKR's large-cap gainers scan had no rows (Utilities and
  Health care on 10-13), and only 6 of the 11 sectors had a card.
- **A biggest-names read that never finished.** It asked for about 75 stocks in one read, which timed out
  ("pool_quotes: TimeoutError") and held the quote thread for most of a minute.

So:

1. **The refreshers keep the board warm.** They run whenever IBKR is connected, not only while the page asks. While
   the page asked within `MARKET_WANTED_SEC` each read keeps its page cadence; otherwise it runs at a slower
   background cadence (`MARKET_IDLE_*_TTL_SEC`). The once-a-session reads (daily closes, prior closes, holdings,
   industries) run in the background as before. The line budget does not change: no line opens with fewer than
   `IBKR_BRIEF_MIN_FREE_LINES` spare, and bars stay at background priority on the paced service.
   `NOVA_MARKET_BOARD_WARM=0` brings back reads only while the page is open. This replaces decision 4's "Its reads
   run only while the page asked within `MARKET_WANTED_SEC`".
2. **IBKR's answers are kept across restarts.** The quotes, ETF and stock quotes, movers, tile lines, prior closes
   and daily closes are written to `board-store.json` at most once every `MARKET_KEEP_SAVE_SEC`, and read back when
   the process starts. Each read's own age rules decide what the page shows and what is read again.
3. **The biggest names are read in chunks** of `MARKET_POOL_CHUNK` stocks, always, not only on the Biggest names
   tab. Each chunk is a short read, so the tile quotes get their turn in between.
4. **A tile with no trade shows its last 5-minute bar's close at any age, with its time.** It is flagged
   `stale: true` once the bar is older than `MARKET_BARS_FRESH_SEC`, and the page dims it with "as of HH:MM". A
   tile's line runs from 04:00 ET to the later of the close and its last point. Crypto lines ask
   `MARKET_LINE_DURATION_CRYPTO`.
5. **Breadth after the close** shows the day's last full sample (volume and TRIN included) from
   `breadth-last.json`.
6. **Every sector has a top-stocks card.** All 11 cards show, and each ranks the sector's scan movers together with
   its biggest names by the period's move. The 1 D leader is the best of the same set. A sector reads "none" only
   when none of those stocks has a price.
7. **The page:** the browser keeps the page's last answer while the page is closed and shows it at once when the
   page opens again. Every stock or ETF symbol opens the Trader. The runners-per-session chart runs the card's full
   width, says each session's runners by theme on hover, and opens a large view.

Rejected: a separate process for the board. It would need its own IBKR client id, would read the same 100 lines
the desk shares, and its bars would queue behind the same pacing. The threads already run off the IB loop and the
socket loop; what made the page slow was when the reads ran and how they were queued, not which process ran them.
Also rejected: holding lines while the page is closed, for the same line budget reason as before.

## Amendment 2026-10-14: say what each number is, every sector card full, Massive fills the gaps

The operator read the page on 2026-10-14 and asked for four things:

- **The tiles.** "I kind of want to see an icon of what it is. If it's gold, I want to see a gold bar ... crude,
  a barrel." Also: "it doesn't even tell you what it is. Is it the last 24 hours?"
- **The sector cards.** Movers cards held one stock (Materials: LIN; Utilities: CEG; Energy: COP), and Real estate
  read "no price yet". "These cards under Movers are just wasting space ... keep the biggest names and the
  small-cap runners."
- **The runners chart.** "Fill out the previous days by using data from Massive", for sessions with no Nova
  recording.
- **Breadth.** "I don't understand the numbers. What is 1,540? I don't understand the up and down stocks."

So:

1. **Each tile shows a picture of what it is.** The pictures are drawn inline (`TileIcon.tsx`): a gold bar, an oil
   drum, a Bitcoin coin, a VIX gauge, the Treasury for the 10-year yield, a badge for each index future (S&P, NDX,
   R2K, DOW), and a balance for small caps against the S&P.
2. **Each line says its hours, as a quote page's 1-day chart does.** The line runs 04:00 ET to the close, or to its
   last point after it. 04:00 sits under the left end, 09:30 under the open tick, and the axis end under the right
   end. The header says "Today, 5-minute line from 04:00 ET". A tile with no line has no axis.
3. **Movers is retired.** Top stocks offers Biggest names (now the default) and Small-cap runners. Every sector card
   lists its five heaviest holdings, priced by IBKR, with `--` until a price arrives. A saved Movers choice opens on
   Biggest names. The large-cap gainers scan still picks each sector's 1 D leader on the sector board.
4. **Massive fills a session Nova did not record.** The day movers index (`backend/day_movers/`) supplies a common
   stock's first +20 / 50 / 100% minute before the close, so a past session with no board in the lens is drawn from
   it as `source: "massive"`.
   - It is drawn lighter and outlined, and its hover card says where the count came from.
   - It feeds no count, baseline, temperature, theme share, gapper rate or runners tab, because it is another lens:
     every listed stock, no top-50 rank. On the 12 sessions from 2026-09-23 to 2026-10-09 that have both, Massive
     counted 60 runners a session against the recorded board's 53, about 13% more. About 76% of the recorded
     runners were also in Massive's list.
   - On 2026-10-13 it filled all seven unrecorded sessions in the chart's 21. Reading 22 sessions took 5.3 s.
5. **Breadth is said in words.** A sentence leads, for example "71% of NYSE stocks are up on the day, and 78% of the
   shares traded were in rising stocks." Each bar carries its counts ("2,012 up", "838 down") over what it counts:
   "of 2,946 NYSE stocks, 96 unchanged". TICK and TRIN read as sentences first and their names second: "412 more
   stocks just ticked up than down"; "buyers heavier: rising stocks draw more volume". The A/D line states its last
   value and which side of the dotted line means more stocks up. The wire is unchanged.

Rejected:

- **Filling only from the rebuilt `market` board** (`MARKET_CLIMATE_USE_REBUILT`). It covers only the days that were
  rebuilt into the leaderboard store, and it ran about 40% hot against the recorded board, not 13%.
- **Mixing Massive days into the averages.** One lens running hotter would read every recorded week as cold.

## Amendment 2026-10-25: is the day hot or cold, the week good or choppy, the month hot or cold

The operator, 2026-10-24: "I need to know if the day is cold or hot. For the week, is it a choppy week, or is it
good? What about the month? We need to start identifying a pattern." Then: "And how do we show it to the user? So
it's a part of the overall decision-making." On 2026-10-25, shown the Day Read, they asked whether it answers that
question. It does not: four of its six checks read the big market, which is a different question. They approved
"upgrade the existing Small-cap climate card with the ... day/week/month rules, show its label at the top of the Day
Read".

The climate's `temperature` was one rule for every period: the period's 20%+ runners a session against their
average, `hot` at 1.25x and `cold` at 0.75x. That counts how many small moves there are, not whether the leaders
are running and money is chasing them, which is what the operator means by a hot day. So:

1. **The temperature is three stated rules, one per period** (`backend/market_board/temperature.py`; thresholds
   `MARKET_TEMP_*`). It reads the climate's lens (the recorded Gainers board's first `MARKET_CLIMATE_RANK_MAX` ranks),
   for stocks whose prior close is $2-20. For each session, minute by minute, it counts **the runners at +100%** and
   **the money in the top 5 gainers**: shares traded times last price for the five with the highest peak gain of 20%
   or more. At the session's last minute it also measures **how many runners held**: of those that peaked at +50% or
   more, the share still keeping half that gain.
   - **Day** (1 D): `hot` with 2 or more runners at +100% and more money than usual; `cold` with no runner at +100%
     and no more money than usual; `warm` otherwise. "Usual" is the median of the prior 60 recorded sessions at the
     same time of day. With fewer than 10 such sessions the day has no label and the card says why.
   - **Week** (7 D, the last 5 sessions): `cold` with 3 or more cold days; `good` with 2 or more hot days and runners
     that held (a mean share of 45% or more); `choppy` when runners faded (under 35%); `ok` otherwise.
   - **Month** (30 D, the last 21 sessions): (hot days minus cold days) divided by labelled days; `hot` at +15% or
     more, `cold` at -15% or less, `warm` otherwise.
   - Today is read so far: every number is as of now, and the usual is taken at the same minute.
2. **The card shows the rule's inputs, not only the word.** For a day, the +100% runners and the money in the top 5
   against the usual. For a week or a month, each session's label as a strip, the runners' hold share and the score.
3. **The Day Read carries the three labels at its top** ("Small caps: cold day · choppy week · hot month"). The
   labels sit apart from the Bullish / Mixed / Bearish verdict and never vote in it, because they answer a
   different question.
4. **A session whose recorded Gainers board holds no row is not a recorded session.** On 2026-10-23 the board was
   `live` for 719 minutes and kept nothing, because IBKR never answered the Gainers scan reopened at 04:00. Counting
   that day would have read it as a cold session with zero runners. Now it reads "no board", like a day Nova did not
   record.
5. **The 1 D "by now" baseline is taken at the session's own clock.** After the session (that evening, overnight, a
   weekend) the minute is the close, not the wall clock's minute. On 2026-10-25 at 01:40 ET the Day Read's runners
   check averaged the prior sessions "by 01:40", got 0, and read "--" with "too few recorded sessions".

Rejected:

- **Taking the counts from the Massive day movers index.** That index is another lens (every listed stock's minute
  bars), it is not live, and the download behind it stops whenever it is paused (2026-10-16 now).
- **True dollar volume.** The board keeps each row's cumulative shares and last price, not its traded value.
  Shares times last price is the same estimate every day, and it is compared only with itself.
- **Folding the big-market checks into the label.** The big market and small-cap momentum are separate questions.
  The Day Read keeps the first as its verdict and the second as the labels.
