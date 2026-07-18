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
| WID-019 | Account | Positions widget | S7 | PositionsPanel and account polling | matched | No material scoped gap | Use the widgets to audit position actions |
| WID-020 | Account | Orders widget with history/export | S15 | Open orders and cancellation in PositionsPanel | partial | Nova lacks complete order history/export and modification workflows | Use the widgets to implement order history before order editing |
| WID-021 | Reports | Performance widget with P&L, win rate, profit factor, duration | S1 | Reports v2, tags, R multiples, drawdown | partial | Metric names, trade-duration views, and drill-down coverage differ | Use the widgets to map Webull performance metrics to Reports v2 |
| WID-022 | Simulation | Paper trading | S2, S9 | IBKR paper Gateway with explicit safety gates | matched | Nova requires local Gateway and preserves broker truth | Use the widgets to audit paper onboarding |
| WID-023 | Workspace | Multi-screen and detachable windows | S3, S10 | Detached Stock View and Electron desktop | partial | Nova does not detach arbitrary modules into independently linked windows | Use the widgets to design detachable module windows |
| WID-024 | Community | Comments widget | S3 | None | not-comparable | Social posting is not part of Nova's local-first trading workstation direction | Use the widgets to keep community features out of execution scope |
| WID-025 | Market overview | Heatmap and broad market-flow widgets | S10, S16 | Dashboard and strategy scanners | missing | No broad heatmap or Webull-style market-flow visualization | Use the widgets to prioritize a market-overview widget |

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

Nova evidence was captured from revision `8c773f0` plus the uncommitted
2026-07-16 workspace. Primary indexes:

- `frontend/src/workspace/registry.ts`
- `frontend/src/ibkr/`
- `frontend/src/chart/`
- `frontend/src/hod_momo/`
- `frontend/src/reports/`
- `backend/routes/trading.py`
- `backend/ibkr/`
- `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`

## Update protocol

1. Read this map and `widgets-memory.md`.
2. Preserve stable capability IDs.
3. Cite dated Webull evidence and a Nova path/test before changing status.
4. Update this ledger before memory or Canvas.
5. Mark stale or unsupported claims `unknown`; never infer parity.
6. Refresh the memory snapshot and `agent-widgets.canvas.tsx`.
