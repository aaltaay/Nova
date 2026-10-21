# Data schema: The heat map

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owner: `frontend/src/heat_map/`. Same
law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1
and #5).

## The heat map on the Trader (ADR 061, operator decision 2026-10-20)

Level 2 over time in place of the Trader's four charts: each tick a line coloured by the shares waiting there, trades
as dots, the book now and volume bars. It reads no endpoint and opens no socket or IBKR line of its own; nothing here
places, stages or blocks an order, and nothing feeds a bot, a setup or a scanner row.

### What it reads (existing frames, unchanged)

- **Level 2** (`/ws/ibkr/depth/{symbol}`, `architecture/schema/execution.md` "Versions"): every `book` frame
  (`data.bids` / `data.asks`, each `{price, size}`; `data.l1_fallback`) as `useIbkrDepth` keeps it, every `beat`
  (the line is alive with no new book), `lent` and `error`.
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
  slot wins). A book wider than `2 x HEAT_MAX_HALF_TICKS` ticks is cut around its middle row (a far-off row cannot drag
  it).
- `bursts[]` (+ the two growing ones): `{t0, t1, sz, pv, side, c0}` -- `side` 0 bought at the ask, 1 sold at the bid,
  2 between or unknown; a burst of buying or selling ends when the other side trades, after `HEAT_BURST_GAP_SEC` (1 s)
  without a print, or `HEAT_BURST_MOVE_TICKS` (2) from its first price. In-between prints form bursts of their own by
  the same pause and move rules, never mixed into buying or selling (approved mockup v3).
- Volume per whole market second (a ring of `HEAT_KEEP_SEC + 120` slots): shares bought at the ask, sold at the bid,
  between.
- `offset` (market time minus the browser clock, from the newest print), `lastBookT`, `aliveT` (newest book or beat),
  `l1`, `line` (`{state: "lent" | "error", why}` or null), `version` (bumped on every change). A line refused or lent
  before the stock's first book or print is kept apart (at most 16 stocks) until a book arrives, so the view says why.

Rules: a book's `t` is the browser clock plus `offset`. When a print moves `offset` by more than `HEAT_REWIND_SEC`
(2 s) -- the first print names a replay's clock; a paused replay held it still -- the books stamped since the previous
print move onto the new clock, except one that would land before that print (it was stamped right), kept in order. A
print more than 2 s behind the newest, or `scrub_reset`, starts the stock over. On a replay's clock (`|offset|` over
`HEAT_REPLAY_OFFSET_SEC`, 60 s) beats are the browser's clock and never stretch the last book; prints move it on (the
recorded book would have changed if it had), and a paused replay is not reported as a quiet line. The last book counts
until `aliveT + HEAT_ALIVE_GRACE_SEC` (2 s); after that the screen is black ("not seen"), never the old book drawn on.
A tick outside a book's rows is "not seen", never an empty level. One screen spans at most `HEAT_MAX_SPAN_TICKS`
(1,200) ticks, cut around the newest middle.

### The switch and the saved choices

`localStorage["nova.heatMap.prefs.v1"]`: `{schema_version: 1, shown: boolean, windowSec: number, minDot: 500 | 1000 |
2000 | 5000, brightness: 0..100}` -- whether the heat map covers the charts (off by default), the window across the
screen (300 s by default; 30-1,800, the 1 / 5 / 15 / 30 minute buttons or the mouse wheel), the smallest burst that
gets a dot (1,000), and the brightness (45: the shares that read red, `10 ^ (5.2 - 1.4 x brightness / 100)`, about
37,000). Missing, malformed, out of range or another `schema_version` reads as the defaults. One setting for every
Trader tab and window; another window's change arrives through the `storage` event.
