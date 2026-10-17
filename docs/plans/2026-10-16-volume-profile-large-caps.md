# Volume Profile for Large Caps Plan

> **Status (2026-10-17): the chart is built (ADR 058, `architecture/schema/volume-profile.md`); the rest is not.**
> On the read card and plan card the operator said "I don't need all of that. I just need the chart", then "go ahead
> and build it! fast forward". Built: §4's switch as the Trader toolbar's Profile button (off until turned on), §5.1's
> engine in `backend/volume_profile/`, and §6.1's 5-minute pane -- today's profile from the draggable 09:30 anchor,
> yesterday's regular session, the boxes, value areas, POC and outlines. Not built: the Settings section, §6.2's two
> drawing tools (the anchor's handle does today's), §5.3-5.5 and §6.3 (zones, shape, reads, the read card, the Large
> Cap columns), §8's signals and §9's research. §13 records the decisions as taken.
>
> **Earlier status (2026-10-16): proposed, not built.** A plan and mockups only, as the operator asked
> ("prepare a complete plan ... do not build it", then "This is only planning phase no code").
> Tracks #1014. Nothing here places, stages or blocks an order.
>
> **Revised the same day** after the operator's review:
> - **The 5-minute chart only.** Operator: "Maybe it's only needed on the 5mins?"
> - **The profile is drawn where it can be seen, on a stated timeline.** Operator: "I can't even see the
>   [anchored] volume profile ... On which chart? Which timeline?"
> - **A research pass,** §9a. Operator: "We may need to do more research."

![Close-up of the 5-minute chart: today's profile in a blue box from the 09:30 anchor to now, its histogram
outlined in its own lane, the value area shaded, the POC in red, and yesterday's profile in a grey box where its
session ended (illustrative prices)](2026-10-16-volume-profile-large-caps-closeup.png)

![The same chart on the whole desk: the zone in play, a pinned signal, the plan, the read card, and the Large Cap
focus list (illustrative prices)](2026-10-16-volume-profile-large-caps.png)

![Settings › Features with the one switch and its three states, the Large Cap columns, and the chart's
Profile menu (where today's profile measures from) (illustrative prices)](2026-10-16-volume-profile-large-caps-switch.png)

*The mockups:*
- They are drawn on Nova's own desk chrome and with Nova's chart library (lightweight-charts 5.1, the chart
  options in `chart/useChartInstance.ts`).
- Prices are made up.
- The profiles, POC, value areas, zones, shape and plan are computed from those made-up candles by the
  method in §5, not typed in.
- The mockup leaves yesterday's after-hours empty so the picture stays clear. On the desk, yesterday's
  profile sits faintly over those after-hours candles (§6.1).

**Goal:** volume profile in Nova for large-cap strategies, as taught in the video the operator chose, with **one
switch that hides or shows all of it**. It covers:
- the profile on the 5-minute chart, and the two drawing tools (anchored and fixed range);
- the zones and the profile's shape;
- two watch-only signals;
- a research reading that decides whether those signals deserve trust.

**Operator ask (2026-10-16):** "I want this feature in nova ... It's going to be for large-cap strategies and I
only want a way to hide that feature and enable it. Go over everything. Let's prepare a complete plan. Give me a
photo PNG image of how it's going to look but do not build it."

**Source:** "NEVER Read Candlesticks Again - Volume Profile Is 10x Better",
https://www.youtube.com/watch?v=Nm5wdUvy0to.
- This session's network policy blocks YouTube.
- The plan works from the transcript the operator pasted and one frame they shared:
  - the profile right-aligned to the price axis, blue next to the axis and yellow outside it;
  - the traded zone as a box with yellow edges and the red POC through it;
  - blue VAH and VAL lines.
- Anything the video only showed, and did not say, is unchecked.

**Architecture:**
- **Backend.** A new pure package, `backend/volume_profile/`, builds the profile from what Nova already holds:
  1-minute bars for every symbol, and prints where they are archived or replayed. One switch module follows
  `leaderboard/auto_record_switch.py`, and one route module serves it.
- **Desk.** A new feature folder, `frontend/src/volume_profile/`, draws on the 5-minute chart with
  lightweight-charts primitives, next to `stock_read/`'s levels.
- **Signals.** The two signals ride the setup scanner as watch-only setups, on a new large-cap lane.
- **Research.** The reading imports the same pure package, so the desk and the backtest compute one profile.

**Nova constraints:**
- *Single market data feed:* live profiles come from IBKR bars and prints only. Massive files feed Sim
  replay and research, never the live desk.
- *Execution gates:* untouched. A signal never places or stages anything. The operator can still stage a
  hand trade from the Plan card, as today.
- *Bots:* none. The operator decided on 2026-09-22 that "bots are for small caps"; a bot on these signals needs
  research, an operator decision and its own ADR. Bots never trade Live, and `auto_live` stays NO-GO.
- *Data first:* `architecture/schema/volume-profile.md` is written before any code (P0).
- *Modularity:* a new owner package and a new owner folder. No logic goes in `main.py` or `App.tsx`.
- *Always-on budget:* no new always-on rule.

---

## 1. What the video teaches, and where each idea lands in Nova

The video's ideas, in our words, with where each one goes.

| # | The idea | In this plan |
|---|---|---|
| 1 | **Effort vs result.** Big candles on big volume are a real move. A small candle on huge volume is **absorption**: a large seller (or buyer) soaking up every order, often before a turn. Price moving on thin volume is **no supply**: it floats, and that is fragile. | §5.5 reads |
| 2 | **Bar colour is not buying or selling.** Every trade has both sides. A volume bar's colour only copies its candle; the height is what counts. | R6 |
| 3 | **Divergence.** New highs on shrinking volume mean the move is running out of fuel, and the mirror holds for lows. | §5.5 reads |
| 4 | **Volume by price, not by time.** The profile turns the histogram 90° onto the price axis. | §5 engine |
| 5 | **400 rows,** not the default 24, so levels are sharp. | §5.1 |
| 6 | **POC, value area, HVN, LVN.** The POC is the most-traded price, a magnet. The value area is about 70% of the volume (VAH on top, VAL below). High-volume nodes are sticky; low-volume nodes are fast lanes. | §5.1–5.3 |
| 7 | **Three tools.** *Anchored* runs from a chosen candle to now. *Fixed range* covers a past stretch, and its POC stays a level. *Session* draws every session by itself. | §6 |
| 8 | **Auction market theory.** Agreement builds high-volume zones; disagreement makes price travel fast through thin areas. Zones hold trapped positions, so price reacts when it comes back. | context, §8 |
| 9 | **Four shapes.** **D**: balanced, fade the edges to the POC. **P**: bullish, buy pullbacks to the POC or the tail's bump, valid only on a close above 50% of the range. **b**: the mirror of P. **Thin**: a news trend, never fade it, join at its small clusters. | §5.4 |
| 10 | **First touch.** The first return to a zone reacts most; later touches fade. | §8.2, tested in §9 (§9a says untested) |
| 11 | **Zones, not lines.** Enter at the zone's edge, not the POC. | §8.2 |
| 12 | **Confirmation.** Price sweeps the thin pocket outside the zone and reaches its edge. A doji, hammer or shooting star then has more volume than the candle before, in the trade's direction, and it has to **close**. Never front-run a forming candle. | §8.2 |
| 13 | **Stops behind the wall, targets before the wall.** Edge to edge across the value area on a reversal. | §8.2 |
| 14 | **Confluence** with classic support and resistance gives the best setups. | §8.2, Nova's `level_map` |
| 15 | **The "80% rule".** When price opens outside yesterday's regular-session value area and is accepted back inside (real closes, not a wick), it tends to cross to the far side. | §8.1, measured in §9 (§9a: about 60%) |
| 16 | **Backtest it yourself.** | §9 |

**Not taken:** the sponsor segment, an order-flow and footprint platform. It is a separate product question,
partly answered by Nova's tape and Level 2 (ADR 034's flow score, `stock_read/bigSeller`).

**One inconsistency, kept as a research cell:** the rule (row 12) has price reach the zone's edge *from
outside*. The video's own long example, though, sweeps *under* the zone and buys a hammer back at its lower edge,
a failed breakdown or "spring". The detector takes the rule as stated.

## 2. What Nova already has

| Fact | Where |
|---|---|
| **Large Cap tab:** one always-live IBKR scan, `TOP_VOLUME_RATE`, market cap over $50B, `CORP` only. | ADR 014; `backend/large_cap_*.py`; `constantGroups/scanner_columns.ts` |
| **Market-cap tiers:** `LARGE_CAP_MIN` is $10B. | `backend/constants_scanner.py` |
| **Trader grid:** 5-Minute, 10-Second, Full Day and 1-Minute panes. The toolbar holds the drawing tools, then EMAs / VWAP / RSI / MACD, then Eyes / Setups / Levels. Each pane has a header (`5-MINUTE`, `5Min`) and a row of chips (`Key`, levels). | `constantGroups/market_ui.ts`, `constantGroups/chart_api.ts`, demo build screenshots |
| **Chart primitives** already draw setups, levels, trend lines, events and fills. | `stock_read/SetupShapesPrimitive.ts`, `stock_read/levelRender.ts`, `chart/*Primitive.ts` |
| **Drawing tools** come from `lightweight-charts-drawing` (Trendline, Horizontal, Vertical, Extended, Ray, Horizontal Ray) and are persisted per chart. | `chart/chartDrawingConfig.ts`, `chart/chartDrawingsStore.ts`, `components/ChartDrawTools.tsx` |
| **The level map:** today's, the 5-minute and the daily support and resistance zones. This is where confluence comes from. | `stock_read/level_map.py`; `stock-read.md`, "The day's levels" |
| **Bars:** 1-minute IBKR history, store-first, from 04:00 ET. **Prints:** `l2.db` `tape_trades`, only for symbols with a tape line. | `market-data.md`, ADR 012; `ibkr/tape_sink.py` |
| **History for research:** every US stock's trades and bars from 2016, the Massive files. | `.claude/skills/nova-market-data` |
| **Switch pattern:** an operator-cache JSON file with `schema_version`, where `.env` always wins and the status poll is the truth. | `backend/leaderboard/auto_record_switch.py`, `pages/records/useAutoRecordSwitch.ts` |
| **Watch-only setups** (the pullback dip, the ABCD). | `architecture/schema/setups.md` |
| **The setup universe is small caps** (the HOD Momo set, price $2–20, float under 20M), so **large caps never reach the setup scanner today.** | `setup_scanner/hooks.py`, `constants_setups.py` |
| **Research gate (L3 kill criteria):** the edge lives in one year; it dies at 2x costs; fewer than 300 trades; permutation p over 0.05; the neighbourhood mostly not positive. A4 (large-cap daily mean reversion) failed. The A4b mega-cap cell (over $200M ADV) reached PF 1.19, in-sample. | `Bot-Trading-Plan.md` §2d, L3 |
| **A name clash:** `stock_read/indicators.volume_profile` already means "volume on green vs red candles", which the video argues against (row 2). | `backend/stock_read/indicators.py:97` |

## 3. Scope

**In:**

| | Piece | Phase |
|---|---|---|
| A | **The switch:** one on/off for everything below. | P1 |
| B | **The profile on large-cap 5-minute charts:** today's, anchored at 09:30 (draggable), in its own lane; yesterday's, where its session ended, with its value area carried into today. | P1 |
| C | **Anchored VP** and **Fixed Range VP** drawing tools, on the 5-minute chart. | P2 |
| D | **Zones (HVN/LVN), shape (D/P/b/thin), volume reads,** the read card, and the Large Cap columns. | P3 |
| E | **Research reading** on the Massive history. | P4 |
| F | **Two watch-only signals:** value-area re-entry, and the zone edge on first touch. | P5 |

**Out:**
- The 1-minute, 10-second and Full Day (daily) charts. They stay exactly as they are, unless P4's
  research gives a reason.
- Orders, bots, Live, footprint and order flow, small caps, any TradingView link, and paid data.

## 4. The switch (the operator's one requirement)

**One switch, one place, kept across restarts, the same in every window.** Mockup 2, panels A and B.

- **Owner:** `backend/volume_profile/switch.py`, modelled on `leaderboard/auto_record_switch.py`.
- **File:** `volume-profile-switch.json` in the operator cache: `{schema_version: 1, enabled: bool, set_at: epoch}`.
  - No file reads as **off**: the feature ships hidden (D1).
  - An unknown version or an unreadable file also reads as off. That is logged and stated in `error`.
- **`.env` always wins:** `NOVA_VOLUME_PROFILE=0` holds it off (`source: "env"`). The switch then says so in
  words: "remove that line and restart Nova to use this switch", the way the auto-record switch does. The
  variable's default lives in `backend/constants_volume_profile.py`.
- **API:**
  - `GET /api/volume-profile/switch` returns `{enabled, source: "operator" | "env" | "default", set_at, error}`.
  - `POST /api/volume-profile/switch {enabled}` answers 409 with those words when `.env` holds it off.
  - The desk-wide status poll carries `volume_profile: {enabled, source}`, so every window and pop-out flips
    within one poll. The POST reply is never taken as the truth.
- **Where:** a new **Settings › Features** section (D5).
  - One row: "Volume profile — large caps".
  - Its options sit under it while it is on: which stocks; where today's profile measures from; rows and
    value area; yesterday's profile on or off; which signals, shorts included; colours.
- **Two levels, never confused:**
  - The **switch** decides whether the feature exists at all.
  - The 5-minute toolbar's **"Profile"** toggle shows or hides it on that chart.
  - With the switch off, the toggle, both tools, every overlay, the read card, the Large Cap columns, the
    Signals feed and the nav entry are gone. The desk looks as it does today.
  - The backend does no profile work while off, and routes answer `{enabled: false}`.
  - Profiles the operator drew are kept and come back.
- **One hook on the desk:** `useVolumeProfileEnabled()`. Every surface asks it, and an E2E test flips the switch
  and checks every surface.

## 5. The engine (backend, pure)

Package `backend/volume_profile/`. Its `__init__.py` opens with the owner docstring.

| Module | Owns |
|---|---|
| `profile.py` | Histogram rows, the POC, the value area, the up/down split. Pure. |
| `zones.py` | HVN and LVN zones and their edges. Pure. |
| `shape.py` | D / P / b / thin and the 50% close rule. Pure. |
| `reads.py` | Effort vs result, divergence, absorption, no supply. Pure. |
| `sources.py` | Which input feeds a profile (bars, prints, a replay), the print policy (§9a), and its precision. |
| `sessions.py` | Today's profile from its anchor, yesterday's regular session, untouched past POCs. |
| `switch.py` | §4. |
| `backend/routes/volume_profile.py` | The routes (§7). |
| `backend/constants_volume_profile.py` | Every number below. |

### 5.1 The profile

- **Input.** The profile is always computed from 1-minute bars or prints, **never from the 5-minute candles
  on screen**. TradingView's session profile does the same on a 5-minute chart (§9a).
  - *Live:* the bar store's 1-minute bars (IBKR). Each bar's volume is spread evenly over its high–low rows
    (`source: "bars_1m"`).
  - *Prints* (`source: "prints"`) are used when the archive holds the symbol's prints for the whole window,
    and always in Sim replay and research.
  - The precision is measured first (§11) and shown on the read card.
- **Up and down volume:** a bar's volume is *up* when it closes at or above its open. The split only colours
  the profile and is never read as buyers vs sellers.
- **Rows:** 400 by default (`VP_ROWS`), at least one tick ($0.01) each. Research fixes the row size before any
  test (§9a).
- **POC and value area:** the POC is the row with the most volume; a tie goes to the row nearest the middle.
  The value area is 70%, grown from the POC two rows at a time toward the heavier side (TradingView describes
  the same walk).
- **Recompute:** on every closed 1-minute bar. The forming bar is not in it until it closes.

### 5.2 Sessions and the timeline (the operator's question)

- **Today's profile** measures from an **anchor**: the 09:30 open by default.
  - The operator drags the anchor to any 5-minute candle (a low, a breakout), or picks 04:00 pre-market from
    the chart's Profile menu (mockup 2, panel D).
  - The anchor is stored per symbol for the day.
- **Yesterday's profile** covers the regular session, 09:30–16:00. It sits where that session ended, and its
  VAH, POC and VAL carry into today as grey dashed lines. These are fixed for the day, and the re-entry rule
  reads them.
- **Untouched POCs:** a past POC no later bar has traded stays drawn until price trades it (CHOSEN).
- **Regular session only** by default. Pre-market and after-hours get no profile unless the menu turns one on.

### 5.3 Zones

The video names no numbers, so these tolerances are **CHOSEN** template parameters, and §9 tests their
neighbourhood.

- **Smoothing:** a centred moving average over `VP_SMOOTH_ROWS` (2% of rows).
- **HVN:** a local peak at or above `VP_HVN_MIN_OF_POC` (50%) of the smoothed POC. Its **zone** is the run of rows
  at or above `VP_HVN_EDGE_OF_PEAK` (60%) of the peak. The zone's top and bottom are its **edges**: the yellow
  entry lines.
- **LVN:** rows at or under `VP_LVN_MAX_OF_POC` (25%) of the POC's volume, between or beyond HVNs. These are
  the fast lanes, and where stops go.
- **Touches** are counted per zone per day after price has left the zone (closed at least
  `VP_SEPARATE_ZONE_WIDTHS` zone widths away), the way the flat top counts touches. **Touch number and the
  zone's age are recorded on every signal,** because the research disagrees with "first touch is best" (§9a).

### 5.4 Shape

The video gives the shapes and the 50% close rule; the rest is CHOSEN.

- **P:** the POC is in the upper third, the lower third holds no more than `VP_TAIL_MAX_PCT` (15%) of the
  volume, **and** the close is above 50% of the range.
- **b:** the mirror of P.
- **D:** the POC is in the middle third, with thinner outer thirds.
- **Thin:** no dominant node. The POC holds less than `VP_THIN_POC_MULT` (2.5x) the mean row, and the value area
  spans more than `VP_THIN_VA_SPAN` (60%) of the range.
- **The read card shows the shape's one-line play,** never enforced until §9 says it helps.

### 5.5 Volume reads

Read rows, not signals. Each says what it read and when.

- **Healthy:** a top-20% volume candle with a body in the top half of its ATR.
- **Absorption:** the same volume, but a body in the bottom 30% of its ATR.
- **No supply:** three or more rising closes, each on below-median volume.
- **Divergence:** three or more new highs (or lows) on falling candle volume.

## 6. On the desk: the 5-minute chart only

New feature folder `frontend/src/volume_profile/`: an ADR 005 `feature`, with a row in `frontend/src/FOLDERS.md`
and an `index.ts` barrel. Mockup 1 shows every piece; the numbers below match its callouts.

### 6.1 The chart

1. **Toolbar.**
   - A **"Profile"** toggle after MACD, in the same chip style as EMAs and VWAP.
   - Two new drawing tools after the line tools: **Anchored VP** (one click) and **Fixed Range VP** (two
     clicks).
   - Neither the toggle nor the tools appear while the switch is off.
2. **Yesterday's profile**
   - It starts at yesterday's 16:00 close and grows to the right, faint, with blue next to the boundary and
     yellow outside.
   - On the desk it overlays yesterday's after-hours candles, which are thin on large caps. The mockup leaves
     them out for clarity.
   - Its label reads "YESTERDAY'S PROFILE 09:30 → 16:00".
   - Its VAH, POC and VAL run into today as grey dashed lines, tagged yVAH, yPOC and yVAL at the start of
     today, with grey axis chips.
3. **The anchor:**
   - a blue dashed line and an "Anchor 09:30" handle at the bottom;
   - a faint blue tint over the span it measures;
   - drag the handle to move it.
4. **Today's profile** in its **own lane after the last candle.**
   - Built with the time scale's right offset, so it **never covers a candle** (the operator's frame shows the
     same layout).
   - **Blue (up) next to the axis, yellow (down) outside it** (the video's colours).
   - Value-area rows brighter.
   - Labelled "TODAY'S PROFILE 09:30 → now".
   - Its POC (bold red) and VAH / VAL (blue) run from the anchor to the axis with coloured axis chips.

**How each profile is framed,** so it can be seen at a glance (operator, 2026-10-16: "I can't even see it ... look
at examples on the web, like borders"):
- **A bordered box** over the span the profile measures: blue for today, from the anchor to the axis; grey for
  yesterday.
- **A title tab on the frame:** over the histogram for today, at the bottom for yesterday.
- **A shaded value-area band** from VAH to VAL inside the box, edged by those lines.
- **Bright value-area rows** and dim rows outside it.
- **A white outline** traced along the histogram's edge, smoothed over 3 rows, so a P, b, D or thin shape reads
  at phone size.
- **A narrow red band** on the POC row.

These follow the common conventions of other profile tools, though the session could not open their pages:
- a value-area box from VAH to VAL across the range;
- separate colours inside and outside the value area;
- a bold POC with a narrow band, extended right;
- NinjaTrader's grey outline around the profile.

Search extracts of community and LuxAlgo scripts:
[LuxAlgo fixed range](https://www.luxalgo.com/library/indicator/kIY0znXs-volume-profile-fixed-range),
[ApexFlow FRVP](https://www.tradingview.com/script/MKcYFqdB-Fixed-Range-Volume-Profile-ApexFlow/),
[ActiveQuants](https://www.tradingview.com/script/10UqNQSQ-Volume-Profile-ActiveQuants),
[a NexusFi thread on outlines](https://nexusfi.com/showthread.php?p=672337).
5. **Only the zone in play** gets a box.
   - It runs from the candle where price left the zone to the lane, with yellow edges (the entry lines) and
     the red POC through it, as in the operator's frame.
   - Every other HVN is only a bracket at the lane's edge.
   - LVNs are not drawn; the profile's thin rows show them.
6. **Signals:**
   - a marker on the candle, with no text on the candle itself;
   - a short tag in clear space;
   - **clicking the marker pins a card** with the checklist it passed and its grade;
   - every one is marked WATCH ONLY.
7. **The plan box** sits between the trigger candle and the lane:
   - entry on the close;
   - stop behind the zone;
   - T1 before the next zone, T2 at the far edge of value, with R multiples.
   - It is drawn the way "Show on chart" draws a hand plan today.
8. **The chips row** gains "Profile · today from 09:30 ▾" (it opens the menu in mockup 2, panel D) and
   "Yesterday's value 230.12–232.42".

**Clutter rules** (from "we are overloading the 1min chart", 2026-09-30):
- one profile lane;
- one boxed zone;
- level names at the start of their lines, not over the profile;
- no marker text on candles;
- EMAs and VWAP stay the operator's choice.

**Colours** live in `constantGroups/volume_profile.ts`:

| | Colour |
|---|---|
| Up volume | `#0a84ff` |
| Down volume | `#ffd60a` |
| POC | `#ff453a` |
| VAH / VAL | `#0a84ff` |
| Yesterday's lines | `#8e8e93`, dashed |

### 6.2 The two drawing tools

- **Anchored VP:** one click picks the anchor candle; it runs to now and grows with each closed bar.
  - Today's automatic profile *is* an anchored profile that Nova anchors at 09:30. Placing the tool on a
    candle moves that anchor rather than adding a second, near-identical profile.
- **Fixed Range VP:** two clicks pick a past stretch of the 5-minute chart.
  - It is drawn right after the stretch with its range faintly tinted (as in the operator's frame).
  - Its POC extends right until price trades it.
- **Where they plug in:**
  - `chart/chartDrawingConfig.ts`, `components/ChartDrawTools.tsx` and the chart context menu.
  - Hotkeys `Alt+A` / `Alt+F`, to be confirmed against `hotkeys-continuity`.
  - Persisted in `chartDrawingsStore` (kind `volume_profile`) and skipped, not deleted, while off.
- **Risk:** `lightweight-charts-drawing` ships fixed tool classes, so these need custom `IDrawing`
  implementations. P2 opens with a prototype.
- **A desk lesson from the mockup:** the chart library answers bar positions only for whole bars inside the
  data. Halves and the empty slots on the right need the bar spacing extrapolated, or everything collapses to
  the left edge.

### 6.3 The read card, the Large Cap columns, the Signals feed

- **The read card "PROFILE · Today from 09:30"** sits in the right column under the Stock Quote, in the
  Plan card's style:
  - shape and its one-line play, with the 50% check;
  - POC, VAH and VAL tiles, and yesterday's value;
  - a three-step story: opened under or over, held inside at, far side at;
  - the zones with their touches, the active one highlighted;
  - the volume reads;
  - the source and rows line.
- **The Plan card** shows the signal's plan, marked WATCH ONLY. "Stage in ticket" remains the operator's own
  hand action, as for any plan.
- **The Large Cap tab and the Focus list:** while the switch is on, the tab gets four columns: **Profile**
  (shape), **vs yesterday's value**, **To POC**, and **Signal · watch only**. The Focus list gets a VP shape
  column.
- **Scanner › Signals › Profile signals:** a feed of time, symbol and signal, with a ✓ or ✕ outcome.

## 7. Wire shapes (into `architecture/schema/volume-profile.md` in P0, before any code)

- `GET /api/volume-profile/{symbol}?kind=today|yesterday&anchor=<epoch>&rows=400`
- `GET /api/volume-profile/{symbol}/range?from=<epoch>&to=<epoch|now>&rows=400`, for fixed ranges.

```json
{
  "schema_version": 1, "enabled": true, "symbol": "AAPL", "kind": "today",
  "anchor": 1792157400, "from": 1792157400, "to": 1792170900, "source": "bars_1m",
  "rows": 400, "row_size": 0.0113, "low": 228.35, "high": 232.85, "total_volume": 18690000,
  "poc": 231.27, "vah": 232.81, "val": 230.43, "value_area_pct": 70,
  "histogram": [[228.356, 4100, 9800], "... [row_price, up, down] x rows"],
  "zones": [{"kind": "hvn", "lo": 231.21, "hi": 231.45, "peak": 231.34,
             "touches": [{"t": 1792167900, "n": 1}], "confluence": ["tested_bottoms"]},
            {"kind": "lvn", "lo": 231.46, "hi": 232.47}],
  "shape": {"kind": "P", "valid": true, "close_pct": 81, "play": "Buy a pullback into the POC zone"},
  "yesterday": {"date": "2026-10-15", "vah": 232.42, "poc": 230.83, "val": 230.12},
  "naked_pocs": [{"date": "2026-10-13", "price": 233.40}],
  "reads": [{"kind": "absorption", "t": 1792165500, "price": 232.62, "words": "big volume, small candle"}],
  "error": null
}
```

- **Off:** `{"schema_version": 1, "enabled": false}`.
- **Unknown or missing:** the response keeps its shape. The profile fields (`poc`, `vah`, `val`, `histogram`,
  `zones`, `shape`, `yesterday`) are `null`, and the top-level `error` says why in words. For example: `{"schema_version": 1,
  "enabled": true, "symbol": "AAPL", "kind": "today", "source": null, "poc": null, ..., "error": "IBKR history did
  not answer for AAPL 1-minute bars"}`. Never a zero, and never a bare `null` with no reason.
- **Large Cap rows** add `vp: {shape, vs_yesterday, to_poc_pct, signal} | null`.
- **Signals** use the setup row of `setups.md`, with kinds `va_reentry` and `vp_zone_edge`.

## 8. The two strategies (watch-only)

Both run on a **new large-cap lane** of the setup scanner.
- **Universe:** the Large Cap tab, plus large caps on the watch list, plus SPY, QQQ and IWM with D3.
- **Cost:** bars only, so no Level 2 or tape line is used. The tape gate reads `blind` and says so.
- **Journal:** every signal is journaled and scored with what price did next.
- **Shorts:** shown with D6, watch-only.

### 8.1 Value-area re-entry: `va_reentry`

- **Arms:** today's 09:30 open is outside yesterday's regular-session value area.
- **Triggers (acceptance), pre-registered: the classic rule.** Two consecutive **30-minute periods aligned to
  09:30** both **close inside** the value area. On the 5-minute chart that is six candles each. One wick inside
  never counts.
- **Variants** (research cells, §9):
  - the first 30 minutes closing inside;
  - two closed 5-minute candles inside;
  - any trade inside versus a close inside.
- **Entry:** the close of the second period. **Target:** the far extreme of yesterday's value area.
- **Stop (CHOSEN; the video names none):** one tick past the day's extreme outside the value area.
- **Fails:** a 30-minute close back outside before the target, or no acceptance by `reentry_by` (12:00 ET,
  CHOSEN).
- **Expectation, from §9a: about 60%, not 80%.**
- **Mockup:** AAPL opens at 228.95, under yesterday's VAL 230.12. It holds inside through the 10:00–10:30
  period and reaches yesterday's VAH 232.42 at 11:15.

### 8.2 Zone edge, first touch: `vp_zone_edge`

- **Zones:** HVN zones from today's profile and yesterday's (§5.3).
- **Arms on the first touch** after price left the zone. Later touches are recorded and are research cells,
  not ignored (§9a).
- **Long, approaching from above** (the short is the mirror):
  1. *Sweep:* price trades through the LVN just above the zone.
  2. *Edge:* price reaches the zone's top edge (within one row or 1 cent).
  3. *Candle:* the closed 5-minute candle at the edge is a **hammer** (lower wick at least 2x the body and at
     least 50% of the range) or a **doji** (body at most 10% of the range) (CHOSEN definitions). It closes in
     its upper half, **on more volume than the candle before**, and **it has closed**.
- **Entry:** **the trigger candle's close** (no front-running); a limit at the edge is a research cell.
- **Stop:** one row (at least 1 cent) past the zone's **far** edge, in the LVN behind it.
- **Targets (two halves, the existing target menu):** T1 is one row before the next HVN; T2 is the far
  value-area extreme.
- **Grade:** **A** when the zone overlaps a `level_map` zone (tested tops or bottoms, yesterday's high or low,
  a whole round, a daily level); **B** otherwise.
- **Shape as context:** a template option, off until §9 decides.
- **Mockup:**
  - After the 11:35 absorption, price falls through the fast lane to the POC zone's top edge, 231.45.
  - A hammer closes at 12:05 on 590K, against 12:00's 360K.
  - Entry 231.70, stop 231.20, T1 232.47 (1.5R), T2 232.80 (2.2R).
  - Graded A: the zone sits on the morning's tested bottoms.

## 9. Research before trust (P4)

A pre-registered reading in the A1–A4 style, frozen first and then run once. It goes in `Bot-Trading-Plan.md` as
**A6, volume profile on large caps**.

- **Data:** Massive trades and 1-minute bars, 2016 onward, split-adjusted, delisted names kept. Profiles are
  built **from trades** by the same `backend/volume_profile/` code.
- **Universe, point in time:** 20-day average dollar volume over $200M (the A4b cell), plus a $50M neighbourhood
  cell. Regular session only.
- **Costs:** as §2b, plus 2x costs.
- **Split:** in-sample 2016–2022, out-of-sample 2023–2026, and nothing tuned on the out-of-sample years.
- **Kill criteria:** L3, unchanged.
- **Measured first, before any rule** (§9a):
  - (a) how far a 1-minute-bar POC and value area sit from a trades-based one on large caps, in cents and as a
    share of ATR;
  - (b) how much the print policy (closing auction, off-exchange, odd lots) moves them.
- **Cells:**
  - **`va_reentry`:**
    - classic two 30-minute periods (primary), first-30-minutes, two 5-minute closes;
    - close inside vs any trade inside;
    - the setup's frequency;
    - a null: a re-entry at a random time.
  - **`vp_zone_edge`:**
    - touch 1 vs 2 vs 3+, and the zone's age;
    - edge vs POC entries;
    - with vs without the volume and sweep filters;
    - grade A vs B;
    - shape filter;
    - the "spring";
    - 1- vs 5-minute candles;
    - the zone thresholds at ±50%;
    - **a random-level control** at matched distances (Osler-style).
- **Passes gate 1:** the signals stay watch-only until the operator decides about a Paper bot, under its own
  ADR.
- **Fails:** the signals stay a scored visual aid, or the operator removes them. The chart profile stands
  either way.

### 9a. What published work says (research pass, 2026-10-16)

The cloud session could not open the pages themselves. These findings come from search-engine extracts, so
treat the attributions as secondhand. Each finding is marked EVIDENCE (measured, with numbers), PRACTICE (what
traders and platforms do) or OPINION.

| Question | Finding | Kind |
|---|---|---|
| Where the "80% rule" comes from | Dalton's market-profile work (*Mind Over Markets*). Classic acceptance is **two consecutive 30-minute periods inside value** after opening outside; the target is the far edge. ([nexusfi](https://nexusfi.com/a/concepts/80-percent-rule), [LuxAlgo](https://www.luxalgo.com/library/concept/80-percent-rule/)) | PRACTICE |
| How often it works | A forum test of 120 days that opened outside value and closed the first 30 minutes back inside: **62.5%** reached the far side. Another test reports about **62%**. LuxAlgo calls 80% "a rule-of-thumb label". **No test on large-cap stocks or SPY found.** ([futures.io](https://futures.io/trading_member/30847-farmertodd.html)) | EVIDENCE (weak) |
| Which timeframe | TradingView's session profile on a **5- to 15-minute chart is computed from 1-minute data**. Market profile classically uses 30-minute periods. Tick-based platforms (NinjaTrader, Sierra Chart) are the most precise. ([TradingView](https://www.tradingview.com/support/solutions/43000703072-session-volume-profile/)) | PRACTICE |
| Bars vs ticks | On 1,088 E-mini S&P days, the 1-minute POC matched the tick POC on about 30% of days and was within 2 ticks on 68%. **Nothing for equities.** ([ABC Trading Group](https://www.abctradinggroup.com/services/research/)) | EVIDENCE (one vendor, futures) |
| Do HVNs and the POC hold | **No peer-reviewed test of volume-profile nodes found.** Related: support and resistance coincide with order-book depth peaks (Kavajecz & Odders-White 2004); published FX levels beat arbitrary ones modestly (Osler 2000). Levels with **more** prior bounces bounced more, and the effect decays over time (Chung & Bellotti 2021, [arXiv](https://arxiv.org/abs/2101.07410)). | EVIDENCE (adjacent) |
| "First touch is strongest" | **Untested.** Practitioner opinion only, and Chung & Bellotti point the other way on touch count. | OPINION |
| Large-cap specifics | About **half of US volume is off-exchange** (TRF 50.6% in 2025, [Cboe](https://www.cboe.com/insights/posts/2025-u-s-equities-year-in-review)). The **closing auction** is about 9–12% of the day in single-price prints ([BMLL](https://www.bmlltech.com/news/market-insight/into-the-close-unpacking-u-s-closing-auction-dynamics-and-the-impact-of-the-russell-reconstitution)), which can make a false node. | EVIDENCE |

**What this changed in the plan:**
- The re-entry rule now uses the classic 30-minute acceptance, with the expectation set at about 60%.
- The profile is computed from 1-minute bars or trades, not the 5-minute candles.
- The bar-vs-trade gap and the print policy are measured before any rule.
- Touch count and zone age are variables, not assumptions.
- The node rules face a random-level control.

## 10. Phases: one PR each

| Phase | Contents | Done when |
|---|---|---|
| **P0** docs | ADR 057, "Volume profile for large caps"; `architecture/schema/volume-profile.md` (§7); AGENTS.md §3 row; `architecture/maintenance-log.md` row; the ADR index row; §13's answers. | The operator confirms the schema (Invariant 1). |
| **P1** switch + engine + 5-minute profile | `backend/volume_profile/` (`profile`, `sessions`, `sources`, `switch`), routes, constants; Settings › Features; the lane, yesterday's profile, the anchor; the status-poll field; `useVolumeProfileEnabled`. | pytest on hand-computed fixtures; Vitest for the primitives; a Playwright E2E proves Off hides every surface and On restores drawings; the bars-vs-prints report (§11); **a desk screenshot set beside mockup 1 before merge.** |
| **P2** the two tools | Anchored VP (moves today's anchor), Fixed Range VP, untouched POCs, persistence, hotkeys. | A prototype first; drawings survive restart and Off/On. |
| **P3** zones, shape, reads, columns | `zones`, `shape`, `reads`; the zone box and lane brackets; the read card; the Large Cap and Focus columns; `level_map` confluence; R6. | Fixtures, card snapshot, `maintainer_checks --gate` green. |
| **P4** research (offline) | A6 harness and report; the measurements in §9 first. Can start once P1's pure engine is merged. | Pre-registration committed **before** the run; the verdict against L3. |
| **P5** watch-only signals | The large-cap lane; `va_reentry`, `vp_zone_edge`; templates; the Profile signals feed; Sim eyes; scoring. | A Sim replay fires both at the research's minute; a test proves no bot family can select them. |
| ~~P6~~ | ~~Paper bot~~. Only if P4 passes **and** the operator asks, under its own ADR. Never Live. | -- |

Every PR runs `py -3 tools/maintainer_checks.py --gate --base origin/master` and carries What / Why this approach /
Verified by.

## 11. How we will know it is right

- **The engine:**
  - hand-built histograms with known POCs and value areas, including ties;
  - an empty range gives a stated `null`, never a zero;
  - the 70% walk against a worked example;
  - the P/b 50% rule on both sides.
- **Bars vs prints:** 20 Massive large-cap days, each built both ways. The report gives how far the POC, VAH and
  VAL differ, in rows, cents and share of ATR. The read card quotes it. Past `VP_BARS_MAX_ERROR_ROWS`, the
  profile uses prints wherever a tape line exists.
- **The switch:** each state below, plus the E2E over every surface.
  - no file;
  - an unknown version;
  - an unreadable file;
  - `.env` holding it off;
  - two windows.
- **The look:** the P1 build is screenshotted against mockup 1 on a real large-cap day, and the operator sees it
  before merge.
- **No order path:** both kinds are in `BOT_WATCH_ONLY_SETUPS`, and no bot family can select them.

## 12. Risks

| # | Risk | Answer |
|---|---|---|
| R1 | Bar-based profiles smear volume across each candle. | Measured in P1 and P4; prints where they exist; the precision shown. |
| R2 | IBKR history budget: 50 large caps x 2 sessions of 1-minute bars. | Yesterday's profile computed once a day and cached; fetches staggered behind the chart panes (ADR 012). |
| R3 | `lightweight-charts-drawing` has no profile tool. | Custom `IDrawing`; P2 prototype first. |
| R4 | The video's claims are untested ("80%", "first touch"). | §9a already says about 60% and "untested"; P4 measures both. |
| R5 | Chart clutter. | The clutter rules in §6.1; the 5-minute chart only. |
| R6 | `stock_read/indicators.volume_profile` means "volume on green vs red", the reading the video calls a myth. | P3 renames it `volume_by_candle_colour`. Whether its read row stays is an **operator question**. |
| R7 | Large caps were never in the setup scanner. | A separate lane with no line cost; the small-cap lanes are untouched. |
| R8 | Every CHOSEN number is ours, not the video's. | Named constants, and §9 tests their neighbourhood. |
| R9 | Off-exchange prints (about half the volume) and the closing auction can move nodes. | A print policy decided and measured in P4 before any rule; the read card names its source. |

## 13. Operator decisions (record them on #1014)

| # | Question | Recommendation |
|---|---|---|
| D1 | When it first ships, is the switch **off** (hidden until you turn it on)? | **Decided 2026-10-17: off.** |
| D2 | What is a large cap: **$10B and up**, or only the Large Cap tab's $50B+? | **Answered by the switch (2026-10-17):** the chart draws on every stock while it is on; a large-cap universe waits for the signals. |
| D3 | Include SPY, QQQ and IWM? | **Answered by the switch**, as D2. |
| D4 | ~~Which chart?~~ | **Decided 2026-10-16: the 5-minute chart only.** |
| D5 | Where the switch lives: a new **Settings › Features**, or Settings › General? | **Decided 2026-10-17: the Trader toolbar's Profile button**, beside Eyes; no Settings section. |
| D6 | Show **short** signals too (watch-only)? | Open: no signals are built. |
| D7 | Today's profile measures from the **09:30 open** by default, or 04:00 pre-market? | **Decided 2026-10-17: 09:30**; the handle drags it to any candle from 04:00. |
| D8 | Re-entry acceptance: the classic **two 30-minute periods**, or faster? | Open: no signals are built. |
