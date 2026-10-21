# Data schema: The heat map

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owner: `frontend/src/heat_map/`. Same
law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1
and #5).

## The heat map on the Trader (ADR 061, operator decision 2026-10-20)

Level 2 over time in place of the Trader's four charts: each tick a line coloured by the shares waiting there, trades
as dots, the book now and volume bars, and since 2026-10-21 the book watcher's word on how each wall left (below). It
reads no endpoint and opens no socket or IBKR line of its own; nothing here places, stages or blocks an order, and
nothing feeds a bot, a setup or a scanner row.

### What it reads (existing frames, unchanged)

- **Level 2** (`/ws/ibkr/depth/{symbol}`, `architecture/schema/execution.md` "Versions"): every `book` frame
  (`data.bids` / `data.asks`, each `{price, size}`; `data.l1_fallback`) as `useIbkrDepth` keeps it, every `beat`
  (the line is alive with no new book), `lent` and `error`.
- **The book watcher's verdicts** on the same socket (`book-watch-and-luld.md`, "What left the book, on the ladder"):
  every `book_watch` frame of `schema_version` 1 -- `source`, `now`, `reset`, `watching`, `reason`, each of `drops[]`
  (`ts`, `side`, `price`, `pulled`, `filled`, `outcome`, `level_before`, `on_approach`) and each of `hidden[]` (`id`,
  `ts`, `side`, `price`, `state`, `hidden`, `printed`, `shown_max`, `started_ts`, `last_print_ts`, `ended_ts`). Another
  `schema_version` is ignored. The same frames the Level 2 ladder folds (`ibkr/bookWatch.ts`); nothing is asked for.
- **Time & Sales** (`/ws/ibkr/tape/{symbol}`): every print of a `print` / `prints` frame -- `time` (ISO; a Sim
  replay's own time, Nova's receipt live), `price`, `size`, `side` (`ask` | `bid` | `between` | `unknown`) -- and
  `scrub_reset`.

### The store (memory only, `heat_map/heatStore.ts`)

Per stock, at most `HEAT_MAX_SYMBOLS` (4; the least recently fed goes first), kept `HEAT_KEEP_SEC` (1,800 market
seconds). Lost on reload; it starts when Nova opens the stock's Level 2 (IBKR keeps no book history).

- `tick`: dollars per row, `0.01`, or `0.001` under $1 (fixed at the stock's first book or print).
- `snaps[]`: `{t, lo, sizes: Float32Array, bb, ba}` -- market time `t`; tick indices `lo`..`lo + sizes.length - 1`
  were inside the rows IBKR sent (IBKR's per-exchange rows summed per tick); `bb` / `ba` best bid / ask tick, `NaN`
  when that side is empty, both taken from the rows kept. At most one per `HEAT_BOOK_SLOT_SEC` (0.1 s; the newest in the
  slot wins). A book wider than `2 x HEAT_MAX_HALF_TICKS` ticks is cut around where the stock trades -- its last print,
  else its last middle; the lower middle row on a first book -- so a far-off row is cut even in a two-row book.
- `bursts[]` (+ the two growing ones): `{t0, t1, sz, pv, side, c0}` -- `side` 0 bought at the ask, 1 sold at the bid,
  2 between or unknown; a burst of buying or selling ends when the other side trades, after `HEAT_BURST_GAP_SEC` (1 s)
  without a print, or `HEAT_BURST_MOVE_TICKS` (2) from its first price. In-between prints form bursts of their own by
  the same pause and move rules, never mixed into buying or selling (approved mockup v3).
- Volume per whole market second (a ring of `HEAT_KEEP_SEC + 120` slots): shares bought at the ask, sold at the bid,
  between.
- `drops[]` (+ `dropKeys`): the watcher's large drops, oldest first, `{key, t, side, price, pulled, filled, traded,
  levelBefore, onApproach}` -- `t` is the drop's `ts`, already market time (Nova's receipt of the book live, the
  recording's own time on a replay); `key` (`ts` to the millisecond, side, price, `level_before`, `level_after`,
  pulled, filled -- two drops at one price in one millisecond differ in their sizes; never `seq`, which a line watched
  again or a rebuilt replay numbers from 1 again) keeps a socket's first frame, which repeats the last minute, from
  adding a drop twice; at most `HEAT_WATCH_MAX_DROPS` (5,000), the oldest going first.
  `hidden`: each hidden stretch's newest word by `id`, `{t0: started_ts, t1: ended_ts | last_print_ts | ts, hidden,
  printed, shownMax, state, said: ts}` (a word older than the one held is ignored). Both go with the keep window and
  with the stock when it starts over; a `reset` replay frame whose `now` is more than `HEAT_REWIND_SEC` behind the newest
  print starts the stock over first (the replay went back). The watcher's `{watching, reason}` per stock (at most 16)
  is kept apart (`heat_map/heatWatch.ts`) so the toolbar can say why there are no marks.
- `offset` (market time minus the browser clock, from the newest print), `lastBookT`, `aliveT` (newest book or beat;
  market time), `depthWallMs` (browser clock of the newest depth frame, book or beat),
  `l1`, `line` (`{state: "lent" | "error", why}` or null), `version` (bumped on every change). A line refused or lent
  before the stock's first book or print is kept apart (at most 16 stocks) until a book arrives, so the view says why.

Rules: a book's `t` is the browser clock plus `offset`. When a print moves `offset` by more than `HEAT_REWIND_SEC`
(2 s) -- the first print names a replay's clock; a paused replay held it still -- the books stamped since the previous
print move onto the new clock, except one that would land before that print (it was stamped right), kept in order. A
print more than 2 s behind the newest, or `scrub_reset`, starts the stock over. On a replay's clock (`|offset|` over
`HEAT_REPLAY_OFFSET_SEC`, 60 s) beats are the browser's clock and never stretch the last book; prints move it on (the
recorded book would have changed if it had). The quiet notice comes from the depth socket going silent -- no book or
beat for `HEAT_ALIVE_GRACE_SEC` + 8 s on the browser clock -- on any venue, so a paused replay that keeps beating stays
quiet and a dropped socket says so. The last book counts
until `aliveT + HEAT_ALIVE_GRACE_SEC` (2 s); after that the screen is black ("not seen"), never the old book drawn on.
A tick outside a book's rows is "not seen", never an empty level. One screen spans at most `HEAT_MAX_SPAN_TICKS`
(1,200) ticks, cut around the newest middle.

### How a wall left, hidden size and the dots' numbers (ADR 061 amendment, operator ask 2026-10-21)

Operator, on a SPCX heat map: "how do I know if that bubble was completely [eaten] ... or did someone remove the wall?
They just spoofed it", then "maybe these bubbles should have #s attached to it? but i know there are hidden
buyers/sellers". Built to approved mockup v4 (`F:/Nova/design/heatmap/v4`, private) with the operator's four picks.
Drawn in the plot over the dots (`heat_map/heatMarks.ts`: `heatMarkLayout` pure, `paintHeatMarks` draws), only from
the verdicts above -- never judged from the picture, where the book trails the tape and a dot spans two cents:

- **How each wall left.** A drop is marked when what stood at its price before it (`levelBefore`, else pulled + filled)
  read at least the ramp's yellow (`HEAT_MARK_WALL_LEVEL`, 0.76) at the current brightness: shares
  `10 ^ (log10(150) + 0.76 x (capLog - log10(150)))`, about 9,900 at 45 and 3,700 at 85, so brightness changes how
  many walls get one. A 3 px cap where the line was cut (slate `#cbd5e1` traded, amber `#f59e0b` pulled -- the ladder's
  colours) and a chip beside it, a bid's under its line and an ask's over it: `✓ 3,719` traded (the filled shares),
  `✕ 2,000` pulled (solid amber, dark digits, when pulled as the price came closer). Marks at one price with one
  verdict closer than `HEAT_MARK_MERGE_PX` (70 CSS px) are one run with one chip: a traded run adds up (`✓ 20.4K`; a
  share trades once), a pulled run shows its biggest pull and how many times (`✕ 2,000 ×2`; an order pulled and put back
  counts each time). Numbers are whole below 10,000, then the ladder's `15.2K`. Chips at one price never overlap and never leave the plot:
  laid left to right after their caps, then packed back from the right edge in the same order.
- **Hidden buyers and sellers.** A violet (`#a78bfa`) dashed box along the price from `t0` to `t1`, cut to the window,
  and `◆ 97.1K hidden` (the watcher's `hidden`) at its end.
- **The dots' numbers.** A buy or sell dot whose radius reaches `HEAT_DOT_LABEL_MIN_R` (11 CSS px, about a fifth of the
  window's biggest dot) carries its shares inside it (`850`, `7.9K`, `52K`). Grey (between or unknown) dots never do:
  they mix midpoint, dark and odd-lot prints, and on a busy stock one grey burst can run for seconds (OLOX 2026-10-21:
  351 prints over 12.5 s).
- **The legend.** `✓ traded`, `✕ pulled`, `◆ hidden` after the dot legend, its hover saying what each means and
  "Hints, never a detection"; while the watcher says `watching: false` the legend dims and its hover gives the
  watcher's reason (`No traded / pulled marks now: ...`).

A mark is the watcher's description of the book, like the ladder's: a hint, never a detection.

### The switch and the saved choices

`localStorage["nova.heatMap.prefs.v1"]`: `{schema_version: 1, shown: boolean, windowSec: number, minDot: 500 | 1000 |
2000 | 5000, brightness: 0..100}` -- whether the heat map covers the charts (off by default), the window across the
screen (300 s by default; 30-1,800, the 1 / 5 / 15 / 30 minute buttons or the mouse wheel), the smallest burst that
gets a dot (1,000), and the brightness (45: the shares that read red, `10 ^ (5.2 - 1.4 x brightness / 100)`, about
37,000). Missing, malformed, out of range or another `schema_version` reads as the defaults. One setting for every
Trader tab and window; another window's change arrives through the `storage` event.
