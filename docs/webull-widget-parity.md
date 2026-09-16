# Webull to Nova Widget Capability Map

Evidence-based map of public Webull stock and day-trading widgets to Nova.
This is the canonical capability ledger for `widgets`; the Canvas is a
dated presentation snapshot, not a source of truth.

## Scope

- Included: U.S. stock/ETF discovery, research, market data, order entry,
  account monitoring, reports, and workspace capabilities relevant to Nova.
- Excluded: options, futures, crypto, bonds, event contracts, funding, and
  account-administration surfaces.
- Webull evidence is research-only. It is never a Nova market-data or order
  source.
- A Webull claim without a current public source remains `unknown`; the
  platform's "45+ widgets" marketing statement is not treated as a complete
  catalog.

## Status vocabulary

- `matched`: Nova offers the atomic capability in the scoped workflow.
- `partial`: Nova has a counterpart but material behavior or coverage differs.
- `missing`: no Nova counterpart exists.
- `nova-only`: Nova capability without a comparable Webull widget.
- `not-comparable`: intentionally outside Nova's product direction.
- `unknown`: evidence is insufficient or stale.

Parity is evaluated separately across visual, functional, data-source, and
operational dimensions. Similar appearance alone is not functional parity.

## Capability ledger

| ID | Category | Webull widget or capability | Evidence | Nova counterpart | Status | Material gap | Implementation request |
|---|---|---|---|---|---|---|---|
| WID-001 | Workspace | Custom layouts with movable/resizable widgets | S1, S3 | Phase H module workspace; `frontend/src/workspace/` | partial | Nova supports visibility, ordering, slots, and saved layouts but not Webull-style arbitrary canvas placement everywhere | Use the widgets to implement freeform widget placement without changing feed ownership |
| WID-002 | Workspace | Linked/synchronized symbol surfaces | S9 | `WorkspaceContext`, Stock View, quote composition | partial | Nova synchronizes core quote surfaces but does not expose user-managed link-group colors across every module | Use the widgets to add explicit symbol-link groups |
| WID-003 | Monitoring | Watchlist widget | S7, S9 | Watchlist tab and `useWatchlist` | matched | No material scoped gap | Use the widgets to audit watchlist parity |
| WID-004 | Quote | Quote widget and bid/ask snapshot | S8 | Quote module and `TickerDetailContent` | matched | Nova intentionally attributes IBKR and metadata sources separately | Use the widgets to audit quote-field parity |
| WID-005 | Chart | Advanced stock chart, indicators, drawings, signals | S1, S2 | `TickerChart`, ChartGrid, overlays, session highlighting | partial | Nova has fewer indicators/drawings and no Webull technical-signal catalog | Use the widgets to prioritize the next chart tool |
| WID-006 | Discovery | Stock screener with saved custom criteria | S2 | Gappers, Gainers, Losers, After Hours, Catalysts, HOD Momo | partial | Nova's scanners are strategy-specific rather than a general saved-condition builder | Use the widgets to design a safe custom screener |
| WID-007 | Discovery | Top gainers and losers | S10 | Gainers and Losers tabs | matched | No material scoped gap | Use the widgets to audit movers columns |
| WID-008 | Research | News widget | S8 | News module, catalysts, news-impact surfaces | matched | Provider coverage and ranking differ | Use the widgets to audit news presentation |
| WID-009 | Research | Financial reports and stock analysis | S1 | Fundamentals, broker grid, catalysts, data-source labels | partial | Nova lacks broad statements, estimates, ownership, and analyst-research depth | Use the widgets to map the next research panel |
| WID-010 | Alerts | Price, volume, news, indicator, and signal alerts | S2 | HOD Momo alerts, Nova OS alerts, outbound channels | partial | Nova alerts are strategy-led and do not expose a general user alert builder | Use the widgets to specify a custom alert builder |
| WID-011 | Order flow | Order Book L2 / Bid and Ask | S2, S3, S12 | IBKR DepthLadder and DAS-style montage | partial | Nova lacks NOII and order-by-order views; entitlement/fallback states are explicit | Use the widgets to audit Level 2 parity |
| WID-012 | Order flow | Time and Sales | S11, S12 | IBKR AllLast Time & Sales module | matched | No material scoped gap; Nova remains open-symbol-only by design | Use the widgets to audit tape controls |
| WID-013 | Order flow | NOII auction imbalance | S3, S12 | None | missing | No IBKR-backed auction imbalance panel | Use the widgets to research an IBKR-only NOII equivalent |
| WID-014 | Trading | Classic Trade / Order Entry | S2, S4, S5, S6 | Shared Nova manual IBKR ticket | partial | Basic Buy/Sell, Market/Limit/Stop, sizing, and hours are covered; trailing, stop-limit, and group-order breadth remains | Use the widgets to implement the next manual order type |
| WID-015 | Trading | Active Trade / TurboTrader customizable one-click grid | S1, S13 | Manual ticket plus Nova hotkeys | missing | No configurable large-button rapid-entry grid | Use the widgets to design TurboTrader-style paper-first controls |
| WID-016 | Trading | Depth-based Price Ladder trading | S1, S13 | DepthLadder is display-only | missing | Clicking a depth price does not stage an order | Use the widgets to add paper-first price-ladder staging |
| WID-017 | Trading | Chart Trading | S1 | None | missing | Orders cannot be staged or adjusted directly on a chart | Use the widgets to design chart-based paper order staging |
| WID-018 | Trading | Trading hotkeys | S1, S14 | Nova hotkeys plus DAS-compatible profile authoring | partial | Imported DAS commands remain authoring-only and the runtime action set is intentionally narrow | Use the widgets to map the next safely executable hotkey |
| WID-019 | Account | Positions widget | S7 | PositionsPanel + per-row Flatten; shared dock **Positions** tab on Trader **and** Scanner (`ScannerDesk`) | matched | Flatten is full-position market exit; not order cancel | Use the widgets to audit position sizing / partial close later |
| WID-020 | Account | Orders history CSV export + multi-day records | S15, S17 | Session Closed Orders (WID-027); no email/CSV export | partial | Webull Desktop Orders → Export / App History → Orders Records CSV still missing; modify-order deferred | Use the widgets to implement CSV export before order editing |
| WID-021 | Reports | Performance widget with P&L, win rate, profit factor, duration | S1 | Reports v2, tags, R multiples, drawdown | partial | Metric names, trade-duration views, and drill-down coverage differ | Use the widgets to map Webull performance metrics to Reports v2 |
| WID-022 | Simulation | Paper trading | S2, S9 | IBKR paper Gateway with explicit safety gates | matched | Nova requires local Gateway and preserves broker truth | Use the widgets to audit paper onboarding |
| WID-023 | Workspace | Multi-screen and detachable windows | S3, S10 | Detached Stock View and Electron desktop | partial | Nova does not detach arbitrary modules into independently linked windows | Use the widgets to design detachable module windows |
| WID-024 | Community | Comments widget | S3 | None | not-comparable | Social posting is not part of Nova's local-first trading workstation direction | Use the widgets to keep community features out of execution scope |
| WID-025 | Market overview | Heatmap and broad market-flow widgets | S10, S16 | Dashboard and strategy scanners | missing | No broad heatmap or Webull-style market-flow visualization | Use the widgets to prioritize a market-overview widget |
| WID-026 | Trading | Post-place Working Orders status (Orders → Working / Today's Orders) | S15, S17, S7 | `WorkingOrdersPanel` on Trading tab + Stock View **Orders (Today)** dock (`orders_today/`) | partial | Segmented Working/Filled/Canceled/Partial/All; highlight after place + cancel; no modify | Keep cancel-only; history is WID-027 / export WID-020 |
| WID-027 | Account | Closed / Filled / Cancelled orders (History → Orders Records lifecycle) | S15, S17 | `closed_orders/` + Orders (Today) Filled/Canceled/Partial segments; `GET /api/ibkr/orders/closed` | partial | Session terminal orders in Orders (Today); Trading tab module still has local filters; no CSV / multi-day | Use the widgets to add CSV export (WID-020) next; keep `auto_live` NO-GO |
| WID-028 | Chart | Chart position / avg-cost display on the open ticker | S7 | `chart/positionOverlay.ts` + avg-cost price line and session fill arrows on every `TickerChart` pane | partial | Cost line from `ib.positions()`; fill arrows from session working/closed orders. Long/Short copy is the HTML badge (WID-029). Not chart trading (WID-017). Working limit/stop orders are not drawn as adjustable chart orders | Use the widgets to add working-order chart lines only after ticket usage evidence |
| WID-029 | Chart | Left-click position badge menu (Close / details) | S7, operator 2026-09-12 | `chart/ChartPositionTag.tsx` + `closeFullPosition` + Positions dock | partial | Close Position is the existing flatten path (PIN / spend / paper-live gates). View Trade Details opens the Positions dock. Ticks Mode and Color Settings omitted -- Nova has no chart tick/color settings | Use the widgets only if an operator asks for badge color or tick-mode display |

## Evidence

Webull sources were captured on 2026-07-16:

- **S1** — [Webull Desktop](https://www.webull.com/trading-platforms/desktop-app):
  customizable layouts, charts, order flow, Price Ladder, TurboTrader,
  hotkeys, chart trading, Performance, news, financial reports, and screeners.
- **S2** — [Webull active trading](https://www.webull.com/active-trading):
  charting, Level 2/NBBO, alerts, Classic Trade, Active Trade, Price Ladder,
  Order Entry, hotkeys, extended hours, paper trading, and supported orders.
- **S3** — [Webull Desktop Native](https://www.webullapp.com/introduce/desktop-native):
  45+ widget claim, Charts, Options, Active Trade, Comments, TotalView, NOII,
  multi-screen support.
- **S4** — [Supported investments and order types](https://www.webull.com/help/faq/298-What-types-of-orders-can-I-place-on-Webull):
  equity Market, Limit, Stop, Stop Limit, Trailing Stop, and group orders.
- **S5** — [Regular and extended hours](https://www.webull.com/help/faq/10960-Regular-and-Extended-Hours-Trading-Sessions):
  Trade-widget hours selector and limit-only extended-hours rule.
- **S6** — [Fractional shares](https://www.webull.com/help/faq/10959-Trading-Fractional-Shares):
  share/USD quantity modes and Classic Trade quantity icon.
- **S7** — [General platform navigation](https://www.webull.com/help/faq/11033-General-Platform-Navigation):
  Positions, Watchlist, and chart order/position display.
- **S8** — [Webull Desktop 4.0 announcement](https://www.webull.com/blog/42-Webull-Financial-Debuts-Customizable-Desktop-Platform-Webull-4-0):
  News, Quotes, Bid and Ask, and customizable Active Trade.
- **S9** — [Webull platform overview](https://www.webull.com/hc/categories/fq4):
  synchronized watchlists, order execution, portfolio monitoring, paper
  trading, charting, and market-data research.
- **S10** — [Webull Desktop 2026 walkthrough](https://www.youtube.com/watch?v=q_2TeFVsn0M):
  public current-product walkthrough for movers, heat maps, layouts, and
  multi-widget workspaces.
- **S11** — [Time and Sales colors](https://www.webull.com/help/faq/1138-What-do-the-different-colors-in-Time-Sales-data-represent):
  trade-at-bid/ask/between behavior.
- **S12** — [Webull market data](https://www.webull.com/help/faq/126-What-market-data-is-available-on-Webull):
  TotalView depth, NOII, market-by-order, and Time and Sales.
- **S13** — [Webull Desktop TurboTrader](https://www.webull.com/learn/3R0xpr/f20iHO):
  TurboTrader plus Price Ladder/DOM course catalog.
- **S14** — [Webull Desktop hotkeys](https://www.webull.com/learn/courseware/jMIB8w/How-to-Use-the-Hotkey-Function-on-Webull-Desktop-Platform):
  configurable general, chart, watchlist, and trading hotkeys.
- **S15** — [Downloading transaction history](https://www.webull.com/help/faq/992-Downloading-Your-Transaction-History):
  Orders-widget history export.
- **S16** — [Market Watch](https://www.webull.com/help/faq/10624-Market-Watch):
  heat-map size and sentiment behavior.
- **S17** — [Order Instructions and Settings](https://www.webull.com/help/faq/291-Where-do-I-place-an-order)
  (captured 2026-07-18): Desktop **Orders → Working** for cancel/modify;
  App **Orders → Open Orders**; Website **Today's Orders → Working Orders**;
  history via Account → Orders / History → Orders Records; optional order
  confirmation toggle; export from Orders widget settings. Lifecycle statuses
  named in S15 export: filled, partially filled, pending, working, cancelled,
  failed. Public docs do not publish an exhaustive column schema; Nova column
  map below is inferred from those lifecycle names + IBKR open-order fields.
  Re-confirmed 2026-07-18 via public S17: Desktop **Orders → Working**;
  Website **Today's Orders → Working Orders**; history via App
  **History → Orders Records**, Desktop Orders widget **Export Orders**,
  Website **Order History → Export**. Public FAQs do not name a literal
  "Closed Orders" tab — Nova's **Closed Orders** maps to the filled/cancelled
  lifecycle + History Records surface (not Working).

Nova evidence was captured from revision `8c773f0` plus the uncommitted
2026-07-18 working-orders and closed-orders work. Primary indexes:

- `frontend/src/workspace/registry.ts`
- `frontend/src/closed_orders/` (WID-027 feature slice — ADR 005)
- `frontend/src/ibkr/`
- `frontend/src/chart/`
- `frontend/src/hod_momo/`
- `frontend/src/reports/`
- `backend/routes/trading.py`
- `backend/ibkr/orders.py` (`open_orders`, `closed_orders`)
- `frontend/src/ibkr/WorkingOrdersPanel.tsx`
- `frontend/src/ibkr/PositionsPanel.tsx` / `TradingTab.tsx`
- `frontend/src/ibkr/closeFullPosition.ts` (Flatten SSOT helper)
- `frontend/src/stock_view/StockViewRail.tsx`
- `architecture/decisions/005-frontend-feature-slices.md`
- `architecture/decisions/007-centralized-trading-execution.md`
- `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`

### Working Orders column map (WID-026)

| Webull concept (S15/S17) | Nova / IBKR field | In Working Orders v1 |
|---|---|---|
| Symbol | `symbol` | yes |
| Side (Buy/Sell) | `side` | yes |
| Quantity | `qty` (`totalQuantity`) | yes — fractional via `formatShareQty` (S6; up to 4 decimals) |
| Filled / partial fill | `filled_qty` (`orderStatus.filled`) | yes — column **Filled** (fractional OK; header + cell tooltips) |
| Remaining / left | `remaining_qty` (+ qty−filled fallback) | yes — **Remaining** (fractional OK; hidden only when `compact`) |
| Order type | `order_type` | yes — UI spells out Limit Order / Market Order / Stop Order (not LMT/MKT/STP) |
| Limit / price | `limit_price` | yes — column **Limit price** |
| Stop | `stop_price` (`auxPrice`) | yes — column **Stop price** |
| Avg fill | `avg_fill_price` | yes — column **Average fill** |
| Status (Working / Pending / Partially filled / …) | `status` (IBKR wire) | yes — mapped via `orderDisplay.ts` (never show PreSubmitted/Submitted raw) |
| Session / extended hours | `outside_rth` | yes — **Regular hours** / **Extended hours** |
| Order id | `order_id` | yes |
| Account | Gateway paper/live mode (status bar) | mode badge elsewhere; not a column |
| Time placed | `submitted_at` snapshot | yes — **Time** (ET, fixed at place) |
| Act on remainder | Fill now | yes -- cancel rest + fill remaining (`fillWorkingOrderImmediately`; RTH market or EH bid/ask limit sweep; not Flatten; hidden in sample preview) |
| Modify order | — | deferred (cancel / Fill now only) |
| History / export CSV | — | WID-020 follow-up |

**Active fill progress (verified 2026-07-19):** Filled / Remaining / Average fill +
**Partially filled** status + **Fill now** are the working-order “actively trade”
surface — not WID-015 TurboTrader. Backend `trade_to_order_row` exposes
`filled_qty` / `remaining_qty` / `avg_fill_price` from IBKR `orderStatus`.

**Primary placement:** Trading tab account column (always visible when connected).
**Secondary:** Stock View bottom **Open Orders** dock (`compact={false}` so
Remaining shows; Fill now / Cancel wired when not in sample mode).

### Closed Orders column map (WID-027)

| Webull concept (S15/S17) | Nova / IBKR field | In Closed Orders v1 |
|---|---|---|
| Symbol | `symbol` | yes |
| Side | `side` | yes |
| Quantity | `qty` | yes — fractional via `formatShareQty` (S6) |
| Filled | `filled_qty` | yes — column **Filled** (fractional OK; partial-cancel qty; header/cell tooltips) |
| Order type | `order_type` | yes — Webull-clean labels |
| Limit / price | `limit_price` | yes |
| Avg fill | `avg_fill_price` | yes — column **Average fill** |
| Status (Filled / Cancelled / Failed) | terminal `status` | yes — All / Filled / Cancelled / Partial cancel filters |
| Cancel working order | — | **no** (lives on WID-026 only) |
| Flatten / close position | Positions Flatten → `closeFullPosition` | companion control on WID-019 (not an order-row action) |
| CSV / email export | — | WID-020 |
| Multi-day History Records | — | WID-020 |

**Primary placement:** Trading tab account column under Working Orders when
Modules → Closed Orders is visible (`CLOSED_ORDERS_MODULE_ID`).
**Isolation:** `frontend/src/closed_orders/` feature slice + workspace registry
entry — hide via Modules menu; ready for future move/drag-drop without
baking into StockViewPage forever.
**Close vs Cancel:** Cancel = DELETE working order. Flatten / Close position =
full exit via `POST /api/ibkr/order` (ADR 007), same as hotkeys `exit_pos`.

## Update protocol

1. Read this map and `widgets-memory.md`.
2. Preserve stable capability IDs.
3. Cite dated Webull evidence and a Nova path/test before changing status.
4. Update this ledger before memory or Canvas.
5. Mark stale or unsupported claims `unknown`; never infer parity.
6. Refresh the memory snapshot and `agent-widgets.canvas.tsx`.
