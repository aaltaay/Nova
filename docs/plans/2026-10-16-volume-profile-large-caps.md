# Volume Profile for Large Caps Plan

> **Status (2026-10-16): proposed, not built.** A plan and a mockup only, as the operator asked ("prepare a
> complete plan ... do not build it"). Tracks #1014. Nothing in this plan places, stages or blocks an order.

![Mockup: volume profile on a large-cap 5-minute chart, the read card, the Features switch and the Large Cap
columns (illustrative data)](2026-10-16-volume-profile-large-caps.png)

*The mockup uses made-up prices on a real symbol. Its profile, POC and value area are computed from those
made-up candles, the way this plan computes them.*

**Goal:** Volume profile in Nova for large-cap strategies, as taught in the video the operator chose, with **one
switch that hides or shows all of it**. It covers:
- a session profile on the charts, and the two drawing tools (anchored and fixed range);
- the zones and the profile's shape;
- two watch-only signals;
- a research reading that decides whether those signals deserve trust.

**Operator ask (2026-10-16):** "I want this feature in nova ... It's going to be for large-cap strategies and I
only want a way to hide that feature and enable it. Go over everything. Let's prepare a complete plan. Give me a
photo PNG image of how it's going to look but do not build it."

**Source:** "NEVER Read Candlesticks Again - Volume Profile Is 10x Better",
https://www.youtube.com/watch?v=Nm5wdUvy0to. The cloud session could not reach YouTube: its network policy denies
the host. The plan works from:
- the transcript the operator pasted;
- one frame they shared: the profile right-aligned to the price axis with blue next to the axis and yellow outside
  it, the traded zone as a box with yellow edges and the red POC through it, and blue VAH/VAL lines.

Anything the video only showed, and did not say, is unchecked.

**Architecture:**
- **Backend.** A new pure package, `backend/volume_profile/`, builds the profile from what Nova already holds:
  1-minute bars for every symbol, and prints where they are archived or replayed. One switch module follows
  `leaderboard/auto_record_switch.py`, and one route module serves it.
- **Desk.** A new feature folder, `frontend/src/volume_profile/`, draws it with lightweight-charts primitives,
  next to `stock_read/`'s levels.
- **Signals.** The two signals ride the setup scanner as watch-only setups, on a new large-cap lane.
- **Research.** The reading imports the same pure package, so the desk and the backtest compute one profile.

**Nova constraints:**
- *Single market data feed:* live profiles come from IBKR bars and prints only. Massive files feed Sim replay and
  research, never the live desk.
- *Execution gates:* untouched. Nothing here can place an order.
- *Bots:* none. The operator decided on 2026-09-22 that "bots are for small caps"; a bot on these signals needs
  research, an operator decision and its own ADR. Bots never trade Live, and `auto_live` stays NO-GO.
- *Data first:* `architecture/schema/volume-profile.md` is written before any code (P0).
- *Modularity:* a new owner package and a new owner folder. No logic goes in `main.py` or `App.tsx`.
- *Always-on budget:* no new always-on rule.

---

## 1. What the video teaches, and where each idea lands in Nova

The video's ideas, in our words, with where each one goes.

| # | The idea | What it means for a trade | In this plan |
|---|---|---|---|
| 1 | **Effort vs result.** Big candles on big volume are a real move. A small candle on huge volume is **absorption**: a large seller (or buyer) soaking up every order, often before a sharp turn. Price moving on thin volume is **no supply**: it floats because nobody is selling, which is fragile. | Reads the move behind the candles | §5.5 volume reads |
| 2 | **Bar colour is not buying or selling.** Every trade has both sides. A volume bar's colour only copies its candle; the height is what counts. | Stop reading green volume as "buyers" | §12 risk R6 (Nova's "Volume on green vs red" row) |
| 3 | **Divergence.** New highs on shrinking volume mean the move is running out of fuel; new lows on shrinking volume mean the selling is drying up. | An early warning, not a trigger | §5.5 volume reads |
| 4 | **Volume by price, not by time.** The profile turns the histogram 90° onto the price axis: how much traded *at* each price. | The core tool | §5 engine |
| 5 | **400 rows.** The default 24 rows blur everything; 400 is sharp enough to trade. | Precision | §5.1 rows |
| 6 | **POC, value area, HVN, LVN.** The POC is the most-traded price, a magnet. The value area is the band holding about 70% of the volume (VAH on top, VAL below). High-volume nodes are sticky and price slows there; low-volume nodes are fast lanes price rips through. | The levels | §5.1–5.3 |
| 7 | **Three tools.** *Anchored* runs from a chosen start to now and keeps updating. *Fixed range* covers a past chunk only, and old POCs from it stay live as levels. *Session* draws every session by itself (paid on TradingView, and the video shows the free tools do the same by hand). | The chart tools | §6.2 tools, §6.1 session profile |
| 8 | **Auction market theory.** Agreement builds high-volume zones; disagreement makes price travel fast through thin areas. Zones hold trapped positions, so price reacts when it comes back. | Why the levels work | context for §8 |
| 9 | **Four shapes.** **D**: balanced, so fade both edges to the POC. **P**: heavy on top, bullish; buy pullbacks to the POC or the tail's small bump, valid only when the period closes above 50% of its range. **b**: the mirror of P, valid only when the period closes below 50%. **Thin**: an explosive news trend with no balance; never fade it, and join at the small clusters inside it. | The context filter | §5.4 shape |
| 10 | **First touch.** The first return to a zone is the one that reacts. Later touches lose force as trapped traders leave. | Only the first touch arms | §8.2 |
| 11 | **Zones, not lines.** Price often turns at the zone's edge and never reaches the POC. Enter at the edge: the top edge for a long coming from above, the bottom edge for a short coming from below. | The entry | §8.2 |
| 12 | **Confirmation.** Price first sweeps the thin pocket just outside the zone and reaches the zone's edge. One candle (doji, hammer or shooting star) then needs volume above the candle before it, in the trade's direction, and it has to **close**. Never front-run a forming candle. | The trigger | §8.2 |
| 13 | **Stops behind the wall, targets before the wall.** The stop goes in the thin area past the far side of the heavy zone, where price only goes when the idea is wrong. Profit is taken at the first edge of the next heavy zone. A reversal trade runs edge to edge across the value area. | Stop and targets | §8.2 |
| 14 | **Confluence.** A profile level on top of an old swing high or low or a respected level is the best setup. | The grade | §8.2, Nova's `level_map` |
| 15 | **The bonus rule (the "80% rule").** When price opens outside the previous regular session's value area and comes back inside, it usually travels to the far side. It needs **acceptance**: real candles closing inside, not one wick. | A second setup | §8.1 |
| 16 | **Backtest it yourself.** A setup that looks perfect on three charts means nothing until it holds over hundreds of trades. | Research before trust | §9 |

**Not taken:** the sponsor segment. It promotes an order-flow platform that rebuilds sliced institutional orders and
shows footprint charts. That is a separate product question, partly answered by Nova's tape and Level 2 (ADR 034's
flow score, `stock_read/bigSeller`). It is out of this plan.

**One inconsistency in the video, kept as a research cell:** the rule (row 12) has price reach the zone's edge
*from outside*. The video's own long example, though, sweeps the thin pocket *under* the zone and buys a hammer at
the zone's lower edge, which is a failed breakdown or "spring". The detector takes the rule as stated, and the
example becomes a variant in §9.

## 2. What Nova already has

| Fact | Where |
|---|---|
| **Large Cap tab:** one always-live IBKR scan, `TOP_VOLUME_RATE`, market cap over $50B, at least 1M shares, `CORP` only (ETFs out). Shows RVOL, ATR expansion, 5D/20D and a score. | ADR 014; `backend/large_cap_*.py`; `constantGroups/scanner_columns.ts` |
| **Market-cap tiers:** `LARGE_CAP_MIN` is $10B. | `backend/constants_scanner.py` |
| **Market page:** large-cap gainers (over $5B) and sector ETFs with their biggest holdings. | ADR 053, `architecture/schema/market-board.md` |
| **Charts:** lightweight-charts v5. The Trader grid has 5-Minute, 10-Second, Full Day and 1-Minute panes; the indicators menu is `CHART_INDICATORS`. | `constantGroups/chart_api.ts`, `constantGroups/market_ui.ts` |
| **Chart primitives** already draw setups, levels, trend lines, events and fills. | `stock_read/SetupShapesPrimitive.ts`, `stock_read/levelRender.ts`, `chart/*Primitive.ts` |
| **Drawing tools:** Trendline, Horizontal Line, Vertical Line, Extended, Ray and Horizontal Ray, from `lightweight-charts-drawing`, persisted per chart. | `chart/chartDrawingConfig.ts`, `chart/chartDrawingsStore.ts`, `components/ChartDrawTools.tsx` |
| **The level map:** today's, the 5-minute and the daily support and resistance zones (tops and bottoms, HOD and LOD, yesterday's high and low, round numbers, SMA200, gaps). This is where confluence comes from. | `stock_read/level_map.py`; `architecture/schema/stock-read.md`, "The day's levels" |
| **Bars:** 1-minute history from IBKR, store-first, from 04:00 ET. | `architecture/schema/market-data.md`, ADR 012 |
| **Prints:** the tape archive `l2.db` `tape_trades`, only for symbols with a tape line. | `ibkr/tape_sink.py` |
| **History for research:** every US stock's trades and bars from 2016, the Massive files, read only through `tools/market_data.py` / `research/market_reads`. | `.claude/skills/nova-market-data` |
| **Switch pattern:** an operator-cache JSON file with `schema_version`, written atomically, where `.env` always wins. The UI shows a refusal in words, and the status poll is the truth. | `backend/leaderboard/auto_record_switch.py`, `pages/records/useAutoRecordSwitch.ts` |
| **Watch-only setups** (the pullback dip, the ABCD): same lanes, journal, scoring and Sim eyes, but no bot trades them. | `architecture/schema/setups.md` |
| **The setup universe is small caps:** the HOD Momo active set, with price $2–20 and float under 20M in the pillars. **Large caps never reach the setup scanner today.** | `setup_scanner/hooks.py`, `constants_setups.py` |
| **Research gate (L3 kill criteria):** the edge lives in one year; it dies at 2x costs; fewer than 300 trades; permutation p over 0.05; the neighbourhood mostly not positive. A4 (large-cap daily mean reversion) failed. The A4b mega-cap cell (over $200M ADV) reached PF 1.19, in-sample only. | `knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md` §2d, L3 |
| **A name clash:** `stock_read/indicators.volume_profile` already exists. It means "volume on green vs red candles", which the video argues against (row 2). | `backend/stock_read/indicators.py:97`, `rows.py:264` |

## 3. Scope

**In:**

| | Piece | Phase |
|---|---|---|
| A | **The switch:** one on/off for everything below. | P1 |
| B | **Session profile** on large-cap 1- and 5-minute charts, with yesterday's regular-session value area. | P1 |
| C | **Anchored VP** and **Fixed Range VP** drawing tools. A past profile's POC stays on the chart until traded. | P2 |
| D | **Zones (HVN/LVN), shape (D/P/b/thin), volume reads**, the read card, and the Large Cap columns. | P3 |
| E | **Research reading** on the Massive history. | P4 |
| F | **Two watch-only signals:** value-area re-entry, and the zone edge on first touch. | P5 |

**Out:** orders, bots, Live, footprint and order flow, small caps, any TradingView link, and paid data.

## 4. The switch (the operator's one requirement)

**One switch, one place, kept across restarts, the same in every window.**

- **Owner:** `backend/volume_profile/switch.py`, modelled on `leaderboard/auto_record_switch.py`.
- **File:** `volume-profile-switch.json` in the operator cache: `{schema_version: 1, enabled: bool, set_at: epoch}`.
  It is rewritten on every change.
  - No file reads as **off**: the feature ships hidden (decision D1).
  - An unknown version or an unreadable file also reads as off. That is logged and stated in `error`, never
    guessed.
- **`.env` always wins:** `NOVA_VOLUME_PROFILE=0` holds the feature off (`source: "env"`), and the switch says so in
  words, exactly as `NOVA_AUTO_RECORD=0` does. The default for the variable lives in
  `backend/constants_volume_profile.py`.
- **API:**
  - `GET /api/volume-profile/switch` returns `{enabled, source: "operator" | "env" | "default", set_at, error}`.
  - `POST /api/volume-profile/switch {enabled}` answers 409 with the words above when `.env` holds it off.
  - The desk-wide status poll carries `volume_profile: {enabled, source}`, so every window and pop-out flips within
    one poll, the way the auto-record switch does. The POST reply is never taken as the truth.
- **Where:** a new **Settings › Features** section, holding one row today: "Volume Profile — large caps", with its
  options under it (D2, D3, colours). Decision D5 is the alternative, Settings › General. It is not a nav-rail
  page: the feature lives where it is used (the charts, the Large Cap tab, the Signals list).
- **Off means off.**
  - The backend stops computing: no profile work, and the large-cap lane is not evaluated.
  - The routes answer `{enabled: false}`.
  - The desk hides the indicator entry, both drawing tools, every overlay, the read card, the Large Cap columns and
    the Signals rows.
  - Profiles the operator drew are **kept** and come back when it is turned on again.
- **One hook on the desk:** `useVolumeProfileEnabled()`. Every surface asks it, so there is one place to get wrong,
  and one test (an E2E that flips the switch and checks every surface).

## 5. The engine (backend, pure)

Package `backend/volume_profile/`. Its `__init__.py` opens with the owner docstring (`package_owner_missing`).

| Module | Owns |
|---|---|
| `profile.py` | Histogram rows, the POC, the value area, the up/down split. Pure. |
| `zones.py` | HVN and LVN zones and their edges. Pure. |
| `shape.py` | D / P / b / thin and the 50% close rule. Pure. |
| `reads.py` | Effort vs result, divergence, absorption, no supply. Pure. |
| `sources.py` | Which input feeds a profile (bars, prints, a replay) and what that costs in precision. |
| `sessions.py` | Today's regular session, yesterday's, the composite of N sessions, and untouched old POCs. |
| `switch.py` | §4. |
| `backend/routes/volume_profile.py` | The routes (§7). |
| `backend/constants_volume_profile.py` | Every number below (§6.1 of AGENTS.md: no magic numbers). |

### 5.1 The profile

- **Input.**
  - *Live:* the bar store's 1-minute bars (IBKR). Each bar's volume is spread evenly across its high–low over the
    rows it covers: the usual bar-based method, and what the mockup does. `source: "bars_1m"`.
  - *Exact:* when the archive holds the symbol's prints for the whole window, volume at price comes straight from
    `tape_trades` (`source: "prints"`), under the same print rules as "Prints that set a price"
    (`market-data.md`).
  - *Sim replay and research:* the replay's or the Massive file's prints (`source: "prints"`).
  - The precision is measured in P1 (§11) and shown on the read card ("1-min bars · IBKR").
- **Up and down volume.** A bar's volume is *up* when it closes at or above its open, *down* otherwise: the colour
  follows the candle (video, row 2). The split only colours the profile and is never read as buyers vs sellers.
- **Rows:** 400 by default (`VP_ROWS`), each row at least one tick ($0.01). An option allows 100–1000.
- **POC:** the row with the most volume. A tie goes to the row nearest the middle of the range (CHOSEN).
- **Value area:** 70% (`VP_VALUE_AREA_PCT`). Start at the POC and add the next two rows on whichever side holds more
  volume, until the area holds 70%. This is the long-standing market-profile method.
- **Recompute:** on every closed 1-minute bar. The forming bar is not in the profile until it closes, and the read
  card says so.

### 5.2 Sessions

- **Today's regular session:** 09:30–16:00 ET. This is the session profile on the charts.
- **Yesterday's regular-session value area:** VAH, POC and VAL, fixed for the day. The re-entry rule (§8.1) and the
  grey dotted lines on the chart use it.
- **Composite:** the last `VP_COMPOSITE_SESSIONS` (5, CHOSEN) regular sessions plus today. Zones that persist come
  from here.
- **Untouched POCs:** a past session's POC that no later bar has traded stays drawn until price trades it (classic
  market profile, CHOSEN). This matches the video's "old points of control still act as strong levels".
- Premarket and after-hours (04:00–09:30, 16:00–20:00) get their own profiles, off by default.

### 5.3 Zones

The video names no numbers, so these tolerances are **CHOSEN**, the way the ABCD's and the flat top's are. They are
template parameters, and §9 tests their neighbourhood.

- **Smoothing:** a centred moving average over `VP_SMOOTH_ROWS` (2% of rows).
- **HVN:** a local peak at or above `VP_HVN_MIN_OF_POC` (50%) of the POC's volume. Its **zone** is the run of rows
  at or above `VP_HVN_EDGE_OF_PEAK` (60%) of that peak. The zone's top and bottom rows are its **edges**: the
  video's entry lines, drawn as the yellow box.
- **LVN:** a run of rows at or under `VP_LVN_MAX_OF_POC` (25%) of the POC's volume, between two HVNs or beyond the
  last one. These are the fast lanes, and where stops go.
- **Touches:** each HVN counts the day's returns to its edge after price left it. "Left" means it closed at least
  `VP_SEPARATE_ZONE_WIDTHS` (1) zone width away. Counting follows the flat top's touch counting
  (`setups.md`, "The flat top counts its touches").

### 5.4 Shape

The video gives the shapes and the 50% close rule. The rest is CHOSEN.

- **P:** the POC is in the upper third of the range, the lower third holds no more than `VP_TAIL_MAX_PCT` (15%) of
  the volume, **and** the period closed above 50% of its range. Otherwise it is "P-like, not valid".
- **b:** the mirror of P: POC in the lower third, the upper third thin, and a close below 50%.
- **D:** the POC is in the middle third, and both outer thirds are thinner than the middle.
- **Thin:** no dominant node: the POC holds less than `VP_THIN_POC_MULT` (2.5x) the mean row, and the value area
  spans more than `VP_THIN_VA_SPAN` (60%) of the range.
- **Each shape carries the video's playbook in one line,** as the mockup's read card shows. The playbook is shown,
  never enforced, until §9 says whether it helps.

### 5.5 Volume reads

These are read rows, not signals. Each says what it read and when.

- **Effort vs result:** a candle in the top `VP_EFFORT_VOL_PCTL` (80th percentile) of the day's volume with a body
  in the top 50% of its ATR reads as **healthy**.
- **Absorption:** the same volume, but a body in the bottom 30% of its ATR ("big volume, small candle").
- **No supply:** price advancing on three or more closed candles, each below the day's median volume.
- **Divergence:** three or more new highs (or lows) on falling candle volume.

## 6. On the desk

New feature folder `frontend/src/volume_profile/`: an ADR 005 `feature`, with a row in `frontend/src/FOLDERS.md`
and an `index.ts` barrel. Other features import it only through that barrel (`cross_feature_import`).

### 6.1 The session profile on the charts (as in the mockup and the operator's frame)

- **Panes:**
  - The 5-Minute and 1-Minute panes of the Trader grid, and any large-cap chart window.
  - **Not** the 10-Second pane, which stays tape-first.
  - **Not** the Full Day pane, which shows only untouched POCs.
  - Nova already heard "we are overloading the 1min chart" (2026-09-30), so the 1-minute pane draws the profile
    narrower and labels zones only on hover.
- **The profile:**
  - Drawn by `VolumeProfilePrimitive.ts`: a lightweight-charts series primitive, behind the candles,
    right-aligned to the price scale, and `VP_PANE_WIDTH_PCT` (about 20%) of the pane wide.
  - **Up volume is blue, next to the axis, and down volume is yellow, outside it.** This is the video's colour
    scheme, picked so the profile never echoes the red and green candles, and the operator's frame shows that
    order.
  - Rows inside the value area are brighter than the rows outside it.
- **Lines:**
  - **POC:** bold red, across the pane, with a red price chip.
  - **VAH and VAL:** blue, with blue price chips.
  - **Yesterday's VAH, POC and VAL:** grey dotted, with grey chips.
  - Colours live in `constantGroups/volume_profile.ts`: `#0a84ff` blue, `#ffd60a` yellow, `#ff453a` red, mapped to
    the theme tokens in `styles/tokens-shell.css`.
- **Zones:** `ZonesPrimitive.ts` draws each HVN as yellow edge lines.
  - The zone a signal is working is a box: a faint fill with the red POC through it, as in the operator's frame.
  - Other zones get dashed, faint edges.
  - LVNs are labelled, not filled.
  - At most `VP_ZONES_SHOWN` (3) zones nearest the price.
- **Toggle:** a "Volume Profile" entry in `CHART_INDICATORS`. It is on by default on large caps while the switch is
  on, and absent while it is off.

### 6.2 The two drawing tools

- **Anchored VP:** one click picks the anchor candle. The profile runs from there to now and grows with every closed
  bar, as in the video. It is drawn like the session profile, at the right edge.
- **Fixed Range VP:** two clicks pick a past range. It draws the range's profile beside the range (with the shaded
  range, as in the operator's frame), and extends its POC to the right until price trades it.
- **Where they plug in:** `chart/chartDrawingConfig.ts`'s tool registry, `components/ChartDrawTools.tsx` and the
  chart context menu, with hotkeys not yet taken (`Alt+A`, `Alt+F`, to confirm against `hotkeys-continuity`).
- **Persistence:** per chart in `chartDrawingsStore`, kind `volume_profile`. While the switch is off they are skipped,
  not deleted.
- **Risk:** `lightweight-charts-drawing` ships fixed tool classes (TrendLine, Ray, …). These two need custom
  `IDrawing` implementations that compute a profile from the bars between the anchors. That is the riskiest desk
  piece, so P2 opens with a prototype.

### 6.3 The read card, the Large Cap columns, the Signals rows

- **Read card** "Volume profile", in the stock read side panel on large caps:
  - the shape with its one-line playbook and the 50% check;
  - POC, VAH and VAL;
  - yesterday's VAH, POC and VAL;
  - the zones with their touches;
  - the two signals with entry, stop and targets;
  - the volume reads;
  - the source and precision line.
- **Large Cap tab:** four columns while the switch is on: **Profile** (shape), **vs yesterday's value** ("opened
  below · re-entered"), **To POC** (%), **Signal**. They live in `constantGroups/scanner_columns.ts` and the
  `large_cap` row type.
- **Scanner › Signals:** the two signals' rows, marked *watch only*, the way the pullback dip and the ABCD are.

## 7. Wire shapes (go into `architecture/schema/volume-profile.md` in P0, before any code)

- `GET /api/volume-profile/{symbol}?kind=session|yesterday|composite&rows=400`
- `GET /api/volume-profile/{symbol}/range?from=<epoch>&to=<epoch|now>&rows=400`
  - fixed range: both ends given;
  - anchored: `to=now`, which the desk re-asks on each closed bar.

```json
{
  "schema_version": 1,
  "enabled": true,
  "symbol": "AAPL",
  "kind": "session",
  "from": 1792157400, "to": 1792170900,
  "source": "bars_1m",
  "rows": 400, "row_size": 0.0113, "low": 228.35, "high": 232.85,
  "total_volume": 21430000,
  "poc": 231.27, "vah": 232.82, "val": 230.32, "value_area_pct": 70,
  "histogram": [[228.356, 4100, 9800], "... [row_price, up, down] x rows"],
  "zones": [{"kind": "hvn", "lo": 231.00, "hi": 231.60, "peak": 231.27,
             "touches": [1792167900], "confluence": ["yday_poc", "whole"]},
            {"kind": "lvn", "lo": 231.62, "hi": 232.36}],
  "shape": {"kind": "P", "valid": true, "close_pct": 79, "playbook": "Buy a pullback into the POC zone or the tail's bump"},
  "yesterday": {"date": "2026-10-15", "vah": 232.60, "poc": 231.10, "val": 229.80},
  "naked_pocs": [{"date": "2026-10-13", "price": 233.40}],
  "reads": [{"kind": "absorption", "t": 1792165500, "price": 232.78, "words": "big volume, small candle"}],
  "error": null
}
```

- **Off:** `{"schema_version": 1, "enabled": false}`.
- **Unknown or missing:** `null` plus `error` in words. Never a zero.
- **Large Cap rows** add `vp: {shape, vs_yesterday, to_poc_pct, signal} | null` (scanner schema).
- **Signals** use the setup row of `setups.md`, with kinds `va_reentry` and `vp_zone_edge`.

## 8. The two strategies (watch-only)

Both run on a **new large-cap lane** of the setup scanner. The existing small-cap universe is untouched.

- **The lane's universe:**
  - the Large Cap tab's roster;
  - plus large caps on the operator's watch list;
  - plus, with decision D3, SPY, QQQ and IWM.
- **Cost:** they need bars only, not a Level 2 or tape line, so they cost no line capacity (Level 1 budget 100,
  depth 3).
- **Tape gate:** reads `blind` for them and says so; a watch-only setup does not need it.
- **Scoring:** every signal is journaled and scored with what price did next, like every setup (ADR 036 amendment).
- **Candles:** the confirmation candle is a closed 5-minute candle (decision D4).
- **Shorts:** short signals are shown with decision D6, watch-only. They never stage an order, and ADR 048's short
  check applies if one ever does.

### 8.1 Value-area re-entry: `va_reentry` (the video's bonus rule)

- **Needs:** yesterday's regular-session VAH and VAL (§5.2).
- **Arms:** today's 09:30 open is outside yesterday's value area. An open under VAL arms a long; an open over VAH
  arms a short.
- **Triggers (acceptance):** `accept_closes` (2, CHOSEN) consecutive closed 5-minute candles **close inside** the
  value area. One wick inside does not count, as the video stresses.
- **Entry:** the second candle's close (the research takes the next bar's open).
- **Target:** the far extreme of yesterday's value area (a long targets VAH).
- **Stop:** one tick past the day's extreme outside the value area (for a long, under the low the open made) (CHOSEN;
  the video names no stop for this rule). The template's `stop_cap` applies.
- **Window:** acceptance by `reentry_by` (11:30 ET, CHOSEN), else it fails.
- **Fails:** a 5-minute close back outside before the target.
- **Mockup:** AAPL opens at 228.95 under VAL 229.80, closes inside at 09:50 and 09:55, and reaches VAH 232.60 at
  11:10.

### 8.2 Zone edge, first touch: `vp_zone_edge` (the video's main setup)

- **Zones:** HVN zones from the composite profile (§5.2–5.3).
- **Arms on first touch only.** Price has left the zone (§5.3) and comes back for the first time today; second and
  later touches are recorded but do not arm (video row 10).
- **Long, approaching from above** (the short is the mirror, approaching from below):
  1. *Sweep:* price trades through the LVN just above the zone, the fast lane.
  2. *Edge:* price reaches the zone's top edge (within `edge_tol`, one row or 1 cent).
  3. *Candle:* the next closed 5-minute candle at the edge is a **hammer** (lower wick at least 2x the body and at
     least 50% of the range) or a **doji** (body at most 10% of the range) (CHOSEN definitions). It closes in its
     upper half (the trade's direction), and **its volume is above the candle before it**. It must close: no
     front-running.
- **Entry:** at the zone's edge (the research tests the edge vs the candle's close).
- **Stop:** "behind the wall": `stop_offset` (1 row, at least 1 cent) past the zone's **far** edge, inside the LVN
  beyond it.
- **Targets (two halves, the existing target menu):**
  - T1 one row **before** the next HVN's near edge ("before the wall");
  - T2 edge to edge: the far value-area extreme.
- **Grade:**
  - **A** when the zone overlaps a `level_map` zone (yesterday's high or low, a tested top or bottom, a whole round,
    a daily level): the video's confluence.
  - **B** otherwise.
- **Shape as context:** a template option, off until §9 decides. P allows longs only at the POC zone or the tail
  bump. b allows shorts only. D allows both edges, with the target the POC. Thin allows no fades.
- **Mockup:** after the rip through the fast lane and the absorption at 11:35, price falls back through the LVN to
  the POC zone's top edge, 231.60. A hammer closes at 12:05 on volume above the 12:00 candle.
  - Entry 231.62, stop 230.92.
  - T1 232.35 and T2 232.80.
  - Graded A: the zone holds yesterday's POC and $231.

## 9. Research before trust (P4): the video's own advice

A pre-registered reading on the research harness, in the style of A1–A4: rules written first and frozen, then run
once. It goes in `Bot-Trading-Plan.md` as **A6, volume profile on large caps**. A5 is SPY swing and is parked.

- **Data:** Massive trades and 1-minute bars, 2016 onward, through `research/market_reads`.
  - Split-adjusted, and delisted names kept.
  - Profiles built **from prints**: the same `backend/volume_profile/` code the desk runs, imported by the harness.
- **Universe, point in time:**
  - 20-day average dollar volume over $200M on the day: the A4b cell, no look-ahead.
  - A $50M cell as the neighbourhood.
  - No index list exists, and today's S&P 500 would be survivor-biased.
- **Costs:** as §2b: $0.01 a share of slippage and IBKR fixed commission. Plus a **2x cost** run.
- **Split:** in-sample 2016–2022 and out-of-sample 2023–2026. Nothing is tuned on the out-of-sample years.
- **Kill criteria (L3, unchanged):** the edge lives in one year; it dies at 2x costs; fewer than 300 trades;
  permutation p over 0.05; the neighbourhood mostly not positive.
- **Cells:**
  - **`va_reentry`:** acceptance in 1, 2 or 3 closes; 5- vs 30-minute candles; the window to 11:30 vs to 16:00. It
    also reports **how often price reaches the far extreme before the stop**: the video's "vast majority" claim.
  - **`vp_zone_edge`:**
    - first touch vs later touches (the video's claim);
    - edge vs POC entries (the video's "zones, not lines");
    - with vs without the volume-above-previous filter;
    - with vs without the sweep;
    - with vs without confluence (grade A vs B);
    - with vs without the shape filter;
    - the "spring" variant (§1);
    - 1- vs 5-minute candles;
    - composite of 3, 5 or 10 sessions;
    - the HVN, LVN and edge thresholds at ±50%.
- **Passes gate 1:** the signals stay watch-only until the operator decides about a Paper bot, which would take its
  own ADR.
- **Fails:** the signals stay what they are, a visual aid with an honest score, or the operator removes them. The
  chart tools stand either way.

## 10. Phases: one PR each

| Phase | PR | Contents | Done when |
|---|---|---|---|
| **P0** | Docs | ADR 057, "Volume profile for large caps"; `architecture/schema/volume-profile.md` (§7); a row in AGENTS.md §3; a row in `architecture/maintenance-log.md`; the ADR index row in `architecture/README.md`; the operator's answers to §13 written in. | The schema is confirmed by the operator (Invariant 1). |
| **P1** | Switch + engine + session profile | `backend/volume_profile/` (`profile`, `sessions`, `sources`, `switch`), routes, constants; Settings › Features; `VolumeProfilePrimitive`; the yesterday's value area lines; the status-poll field; `useVolumeProfileEnabled`. | pytest for the engine on hand-computed fixtures; Vitest for the primitive; a Playwright E2E proves Off hides every surface and On brings back saved drawings; the bars-vs-prints precision report (§11). |
| **P2** | The two tools | Anchored VP and Fixed Range VP (custom `IDrawing`), untouched POCs, persistence, hotkeys. | Prototype first; drawings survive a restart and an Off/On. |
| **P3** | Zones, shape, reads, columns | `zones`, `shape`, `reads`; `ZonesPrimitive`; the read card; the Large Cap columns; `level_map` confluence; the name clash fixed (R6). | The shape and zone fixtures; the read card snapshot; `maintainer_checks --gate` green. |
| **P4** | Research (offline) | The A6 harness and report in `Bot-Trading-Plan.md`. Can start once P1's pure engine is merged, alongside P2 and P3. | Pre-registration committed **before** the run; the verdict against L3. |
| **P5** | Watch-only signals | The large-cap lane; `va_reentry`, `vp_zone_edge`; templates; Signals rows; Sim eyes; scoring. | A Sim replay of a past day fires both at the minute the research found; no order path is reachable (test). |
| ~~P6~~ | ~~Paper bot~~ | **Not in this plan.** Only if P4 passes **and** the operator asks, under its own ADR. Never Live. | -- |

Every PR runs `py -3 tools/maintainer_checks.py --gate --base origin/master` and carries What / Why this approach /
Verified by.

## 11. How we will know it is right

- **The engine.** Hand-built histograms with a known POC and value area. Ties. One-row and empty ranges (a stated
  `null`, never a zero). The two-rows-at-a-time 70% walk checked against a worked example. The P/b 50% rule on both
  sides.
- **Bars vs prints.** On 20 Massive large-cap days, build each regular session both ways and report how far the
  bar-based POC, VAH and VAL sit from the prints-based ones, in rows and cents. The read card's precision line
  quotes that number. If bars miss by more than `VP_BARS_MAX_ERROR_ROWS`, the session profile asks for prints where
  a tape line exists.
- **The switch.** Each case below, then the E2E: Off hides the menu entry, both tools, the overlays, the card, the
  columns and the Signals rows, and On restores them with the drawings intact.
  - no file;
  - an unknown version;
  - an unreadable file;
  - `.env` holding it off;
  - two windows.
- **The desk at a glance.** The P1 build is compared against the mockup above, and the operator gets a screenshot
  before merge.
- **No order path.** A test proves the two setup kinds are in `BOT_WATCH_ONLY_SETUPS`, and that no bot family can
  select them.

## 12. Risks

| # | Risk | Answer |
|---|---|---|
| R1 | Bar-based profiles smear volume across each candle's range. | Measured in P1 (§11). Prints where they exist. The precision is shown, never hidden. |
| R2 | IBKR history budget (60 requests per 10 minutes): 50 large caps x 6 sessions of 1-minute bars. | Yesterday's and older profiles are computed once a day and cached (they never change). Fetches are low priority and staggered behind the chart panes (ADR 012). |
| R3 | `lightweight-charts-drawing` has no profile tool. | Custom `IDrawing`; P2 opens with a prototype. |
| R4 | The video's claims are untested ("vast majority", "first touch"). | P4, pre-registered, before any trust. |
| R5 | Chart clutter. | The 10-Second pane is excluded; at most 3 zones; labels on hover on the 1-minute pane; one toggle. |
| R6 | `stock_read/indicators.volume_profile` already means "volume on green vs red", the reading the video calls a myth. | P3 renames it to `volume_by_candle_colour` (wire key kept for one release). Whether that read row should stay is an **operator question**, not decided here. |
| R7 | Large caps were never in the setup scanner. | A separate lane with its own universe and no line cost. The small-cap lanes are untouched. |
| R8 | Every number in §5 and §8 marked CHOSEN is ours, not the video's. | Each is a named constant or template parameter, and §9 tests its neighbourhood. |

## 13. Operator decisions (record them on #1014; nothing in P1 starts until D1–D5 are answered)

| # | Question | Recommendation |
|---|---|---|
| D1 | When it first ships, is the switch **off** (hidden until you turn it on) or **on**? | **Off.** |
| D2 | What is a large cap: **$10B and up** (Nova's tier), or only the Large Cap tab's **$50B+**? | **$10B.** The tab's roster still feeds the signals' lane. |
| D3 | Include index ETFs (SPY, QQQ, IWM)? | **Yes.** Volume profile is used most on index products; the Live Trader and the Market page already treat ETFs apart. |
| D4 | Confirmation candles: **5-minute** or 1-minute? | **5-minute**, with 1-minute as a research cell. |
| D5 | Where the switch lives: a new **Settings › Features**, or Settings › General? | **Settings › Features**: one home for whole-feature switches. |
| D6 | Show **short** signals (watch-only) too? | **Yes.** The video teaches both sides; watch-only places nothing. |
