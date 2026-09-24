# What each `frontend/src/` folder owns

Read this before adding a file: new code goes in the folder that owns its
concept. No folder owns it? Make one and add its row here in the same change.
`tools/maintainer_checks.py` fails CI when a folder has no row or a row names a
folder that is gone (`folder_owner_missing` / `folder_owner_stale`), so this
list cannot drift from the tree. `py -3 tools/module_map.py` prints it next to
the backend packages.

**Kind** is the ADR 005 layer (`architecture/decisions/005-frontend-feature-slices.md`):

- `feature` -- a product slice. It may import `shared` code, workspace public
  contracts and its own internals, and another feature only through that
  feature's public barrel (`../chart`, never `../chart/barsStore`). A deep import
  into another feature is a `cross_feature_import`; the count is frozen in
  `tools/maintainer_lib/baselines.json`, so a new one fails CI.
- `shared` -- plumbing any layer may import. It must not import feature internals.
- `app` -- page composition and the app shell.

| Folder | Kind | Owns |
|---|---|---|
| `account/` | feature | The Account page: practice-ledger history, equity curve, positions / orders, P&L components, calendar and the details column. |
| `activity/` | feature | The activity trail: the order and Gateway event timeline on the Trading tab's activity dashboard. |
| `advise/` | feature | The Advise overlay: per-symbol advice runs, cost estimate, streamed transcript and a ticket prefilled from the advice. |
| `api/` | shared | HTTP plumbing: the `novaFetch` wrapper that attaches the Nova API key, plus the sensor REST client. |
| `assets/` | shared | Static images: a hero image and the default Vite / React logos (scaffold leftovers). |
| `bot/` | feature | The Bots page: level, arm / allowlist, risk and kill-switch cards, proposals inbox, playbook, session polling. |
| `capture/` | feature | Session Record state on screen: the recording chip, top-edge hairline, stop toast and hold-to-stop button. |
| `chart/` | feature | The ticker chart: chart instance, bars store, drawings, context menu, position overlay, VWAP and session shading. |
| `closed_orders/` | feature | The Closed Orders module: today's closed orders table, filters, recency and the close-position button. |
| `components/` | shared | Shared UI: shadcn `ui/` primitives plus app chrome (GlobalAppBar, NavRail), the scanner table, news / catalyst and settings parts. Mixed -- prefer a feature folder for new feature UI. |
| `constantGroups/` | shared | UI constants grouped by domain (API URLs, desk, scanner columns, bot, practice, theme), re-exported by `constants.ts`. |
| `desk/` | feature | The Desk board: the Scanner condensed to one column beside the Trader workspace. |
| `desktop_update/` | feature | The desktop app's update notice (a newer Nova is out: Update / Later, then Restart to update) and the What's new card of release notes, fed by the Electron main process. |
| `earnings/` | feature | The Earnings tab: the earnings calendar with day bands and before-open / after-close lanes. |
| `electron/` | app | Tests only: Vitest suites for the Electron main-process modules in `frontend/electron/*.mjs`. |
| `execution_latency/` | feature | The execution latency dashboard: operation / segment timings, order-hop and fill evidence, browser timing samples. |
| `focus_report/` | app | The operator's focus report (ADR 033): each window posts its page, symbol, Windows focus and last input to `POST /sensors/focus`, read back as sensor 19. |
| `hod_momo/` | feature | The HOD Momo scanner: alert stream, dock and strip, strategy configurator, master gate, blocklist, debug panel, Running Up tab. |
| `hooks/` | shared | Cross-feature React hooks: scanner data and price stream, ticker stream, news impact, catalysts, alert channels, resizable panels. |
| `hotkeys/` | feature | Hot keys and Nova Actions: bindings editor, DAS import, shortcuts menu, quick-trade bar, actions sent through the manual order path. |
| `ibkr/` | feature | The trading surface: order ticket and placement, working orders, positions, depth ladder, time & sales, Gateway status, trading prerequisites. |
| `issue_report/` | feature | File an issue from the desk: the form (Bug / Feature, optional title and description, the desk details and a scrubbed diagnostics dump), opened from the What's new card and Help > File an Issue…; the backend files it on GitHub. |
| `leaderboard/` | feature | The Scanner board replayed at the Sim playhead: per-minute leaderboard fetch, coverage, lanes, recorder toast. |
| `lib/` | shared | The shadcn `cn()` class-merge helper only. |
| `modules/` | feature | Trader modules the registry mounts: Level 2, time & sales, charts, news, quote header, fundamentals, data sources, watchlist strip. |
| `nova_news/` | feature | The Nova News page: headline desk with masthead, lead story, columns and story filtering. |
| `orders_today/` | feature | The Orders (Today) view: Working / Filled / Canceled / Partial segments in the Stock View footer dock. |
| `pages/` | app | Page composition: Dashboard, Desk, Account, Records, Stock View and sample pages, plus the nav-rail page host. |
| `perf/` | shared | The performance recorder's client side (ADR 026): frame meter, long frames, counters, render counts, the `/api/perf/client` reporter. |
| `practice/` | feature | The practice account (ADR 020): Paper / Sim account model, buying power, reset, fixtures, the Sim account clock. |
| `reports/` | feature | The Reports tab: P&L calendar, month detail, drawdown, R-multiples, tag performance, journal import. |
| `sample_data/` | app | The sample desk (`?view=sample`): sample shell and context, fixtures, mode badge, network gate and order guard, and its own in-memory workspace -- Trader tabs, Focus rail, Desk and pop-out -- behind a storage gate that keeps it off the operator's saved state. |
| `scanner/` | feature | The Scanner page board: row shape gate, REST envelope, filters, pinned rows, replay label, header / footer, desk stack. |
| `screen_record/` | feature | The trading screen recording's header chip (ADR 035): quiet while every monitor records, loud when one does not, fed by the Electron main process. |
| `sensors/` | feature | The sensor board: backend sensor readings, freshness and status chips, shown in the Settings workspace. |
| `settings/` | feature | The Settings overlay: general, account, practice, trade-defaults and order-preference sections; prefs export. |
| `setups/` | feature | The setup scanner (ADR 022, ADR 031): every setup's live board over `/ws/setups`, the words and hovers each state is said in, alert cards, scoreboard, sound, ticket staging. |
| `sim/` | feature | The Sim venue's replay: session strip and scrubber, day picker, Sim clock, historical downloads, depth / tape / capture replay. |
| `stock_read/` | feature | The bot's read on one stock (ADR 036): the plan on top of Level 2 (entry, stop, a 2:1 target, the size the operator's risk per trade buys, Stage in ticket), the seven signal tiles and their hovers, the read sheet (every signal, the bot's decisions on the symbol today, its history), and the setups and levels drawn on the Trader tab's charts. |
| `stock_view/` | feature | The Trader (Stock View) chrome: symbol tab strip, right rail with quote / L2 / ticket, focus rail, footer dock, market clock. |
| `strategy/` | feature | Misnamed: the Contenders tab (id `watchlist`: the ranked Five Pillars table, Journal, Backtest panel) and the Nova OS attention strip. |
| `styles/` | shared | Global CSS by surface: tokens, Tailwind theme / overrides, global app bar, nav rail, scanner, stock view, settings. |
| `table_sort/` | shared | Click-to-sort table headers for every table: the one sort rule (text A to Z first, numbers highest first, flip, then the table's own order; missing values last), the `useTableSort` hook that remembers each table's sort, and the `SortTh` header cell. |
| `testSetup/` | shared | Vitest setup: the guard that keeps tests off the live backend, and the React `act()` flag. |
| `theme/` | shared | Light / dark theme prefs and the `useTheme` hook that sets `data-theme` on `<html>`. |
| `types/` | shared | Shared wire types: ticker, scanner, market, earnings, health, catalysts, news impact, Nova News, desktop bridge. |
| `utils/` | shared | Generic helpers (formatting, prefStore, sorting, rAF coalescing) plus backend / desktop glue (auto-heal, Gateway launch, window bounds). |
| `ux/` | shared | The app-wide dialog service (the alert / confirm / prompt API and the `AppDialogHost` that renders it) and the two tips: why a control is locked (`whyTip`) and what a chip means (`hoverTip`); and Ctrl+F, the find bar every window gets (`findBar`, searching with `findText`). |
| `volume_boost/` | feature | The Volume Boost scanner tab: exceptional L1 volume-rate spikes with age formatting. |
| `watch_list/` | feature | The operator's hand-picked Watch list: the persisted list, the Watch list tab, the watch eye, and the toasts for watched symbols -- "hit HOD Momo" and a setup climbing its ladder on the setup scanner. |
| `workspace/` | feature | The workspace shell: selected-symbol context, module registry, layout / visibility / nav-rail stores, scanner tabs, the pop-out window bus. |
