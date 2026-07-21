# Task log index

Newest first. Full narratives live in sibling `YYYY-MM-DD-*.md` files.

| Date | Entry | One-line summary |
|------|-------|------------------|
| 2026-07-21 | [Bidirectional IBKR Gateway auto-detect (paper↔live heal)](2026-07-21-bidirectional-ibkr-gateway-auto-detect.md) | Bidirectional IBKR Gateway auto-detect (paper↔live heal) |
| 2026-07-20 | [Execution/executor/routes-trading tests leaked real env + real bootstrap](2026-07-20-execution-test-env-leak-fix.md) | assert_orders_allowed read real IBKR_GATEWAY_MODE; TestClient lifespan ran real bootstrap into strategy.risk singleton |
| 2026-07-20 | [IBKR disconnect foresight: sticky intent + port diagnostics](2026-07-20-ibkr-disconnect-foresight.md) | Sticky intentional mode; refuse-only heal; disconnect_hint + UI CTA |
| 2026-07-20 | [Global pretty app dialogs replace native popups](2026-07-20-global-app-dialogs.md) | confirmApp/alertApp/promptApp + AppDialogHost; no window.confirm left |
| 2026-07-20 | [Intentional Paper-Live Gateway switch](2026-07-20-intentional-gateway-mode-switch.md) | Intentional Paper-Live Gateway switch |
| 2026-07-20 | [Paper Place CTA + hot banner](2026-07-20-paper-trading-cta-banner.md) | Orange Place Paper order + top PAPER TRADING banner when mode=paper |
| 2026-07-20 | [Flatten long_qty SSOT + BuyingPower fail-closed](2026-07-20-flatten-long-qty-ssot.md) | positions() SSOT for qty/gates; POSITION_UNAVAILABLE; accountValues raise; FE error gate |
| 2026-07-20 | [Flatten dual-source position SSOT daddy audit](2026-07-20-flatten-dual-source-daddy-audit.md) | Parallel execution+maintainer; reject validate→portfolio; long_qty SSOT on positions() |
| 2026-07-20 | [Flatten position-qty dual-source audit](2026-07-20-flatten-position-qty-dual-source-audit.md) | UI portfolio vs gate positions(); reject validate-only / source=flatten; one net_long_qty SSOT |
| 2026-07-20 | [Vitest act() environment warning audit](2026-07-20-vitest-act-environment-audit.md) | Missing IS_REACT_ACT_ENVIRONMENT disables real-bug warning too, not just noise; affects 24 files not 2 |
| 2026-07-20 | [Shared money formatter (formatMoney)](2026-07-20-shared-money-formatter.md) | Extracted 5x duplicated fmtDollar into single formatMoney utility |
| 2026-07-20 | [Fractional share qty display in trading tables](2026-07-20-fractional-share-qty-display.md) | Webull-style fractional qty in Positions/Orders tables |
| 2026-07-20 | [VCIG late HOD fire: new-high gate vs Running Up](2026-07-20-vcig-hod-retest-gate.md) | HOD strategies need fresh new high; VCIG Squeeze was retest |
| 2026-07-20 | [Header Gateway shows PAPER vs LIVE; point Nova at live Gateway](2026-07-20-gateway-paper-live-badge.md) | Header Gateway shows PAPER vs LIVE; point Nova at live Gateway |
| 2026-07-19 | [Dual listing flags, aux API chips, Alpaca RVOL label](2026-07-19-dual-listing-aux-chips-rvol-label.md) | Side-by-side listing; aux API chips; Alpaca RVOL badge (swap deferred) |
| 2026-07-19 | [Nova OS judgment moved to Stock View dock tab](2026-07-19-nova-os-dock-tab.md) | Judgment panel → dock Nova OS tab; charts reclaim header space |
| 2026-07-19 | [Harvested Warrior materials vs AI / trading decision wiring (current truth)](2026-07-19-harvested-materials-ai-decision-wiring.md) | Whisper harvest on disk unused; Pinecone=slides+official only; no trading auto-consume |
| 2026-07-19 | [Alpaca API usage inventory (discovery=ibkr ops)](2026-07-19-alpaca-usage-inventory.md) | Yes: news + listing + scanner RVOL bars + health; not live prices when ibkr |
| 2026-07-19 | [Warrior transcript harvest → KB / automation / AI plan](2026-07-19-warrior-transcript-kb-plan.md) | Plan: gitignored store → Pinecone (official first) → agents; no vault dump |
| 2026-07-19 | [Isolated Sample data route](2026-07-19-sample-data-route.md) | Header switch → ?view=sample fixtures; never mixes with live |
| 2026-07-19 | [Trader always-on Nova OS judgment](2026-07-19-trader-nova-os-brain.md) | Decide band under Trader header; gates + news_impact ratings |
| 2026-07-19 | [Account header replaces Trading tab](2026-07-19-account-header-replaces-trading.md) | Trading→Account in header; Reports nested; L2/ticket removed |
| 2026-07-19 | [Orders Time Placed audit-grade timestamps](2026-07-19-orders-time-placed-audit.md) | Time→Time Placed; broker+Nova wall stamp; no fill drift |
| 2026-07-19 | [Rename Stock View window to Trader](2026-07-19-rename-stock-view-to-trader.md) | User-facing Stock View → Trader; internals unchanged |
| 2026-07-19 | [Stock View Positions dock (WID-019)](2026-07-19-stock-view-positions-dock.md) | Bottom-dock Positions tab; mounts without waiting on ticker WS |
| 2026-07-19 | [Orders (Today) Webull-style segmented dock](2026-07-19-orders-today-segmented-dock.md) | Working/Filled/Canceled/Partial/All in Stock View |
| 2026-07-19 | [Closed Orders recent completion highlight](2026-07-19-closed-orders-recent-highlight.md) | Amber pulse for rows completed in last 60s |
| 2026-07-19 | [Daddy: Filled / active-trade field audit + polish](2026-07-19-filled-active-trade-daddy-dispatch.md) | Daddy: Filled / active-trade field audit + polish |
| 2026-07-19 | [Tester verify: Filled polish (tooltips) Open/Closed Orders](2026-07-19-filled-polish-tester-verify.md) | Vitest 42 + pytest L2 12 PASS; tooltip titles on Filled/Remaining; no layout regress |
| 2026-07-19 | [Filled / active-fill progress verify](2026-07-19-filled-active-trade-verify.md) | Already-had Filled/Remaining/Fill now; tooltip polish only; not WID-015 |
| 2026-07-19 | [Orders testing pyramid L1-L4](2026-07-19-orders-test-pyramid.md) | Vitest + API contract + mocked Playwright + human paper checklist |
| 2026-07-18 | [IBKR paper hard-pin (no accidental live)](2026-07-18-ibkr-paper-hard-pin.md) | Never heal paper→live; managedAccounts DU/DF pin + spend refuse |
| 2026-07-18 | [Fill now + EH flatten + Cancel+Flatten hotkey](2026-07-18-fill-now-cancel-flatten.md) | Fill now on working orders; MKT EH; cancel_and_exit hotkey |
| 2026-07-18 | [Daddy dispatch: Closed Orders WID-027 + Close SSOT](2026-07-18-closed-orders-widget-dispatch.md) | Daddy dispatch: Closed Orders WID-027 + Close SSOT |
| 2026-07-18 | [WID-027 Closed Orders widget verification](2026-07-18-wid-027-closed-orders-verify.md) | Scoped pytest/Vitest/build PASS; Flatten gated; live API needs reload for /orders/closed |
| 2026-07-18 | [Closed Orders widget (WID-027) + Flatten SSOT](2026-07-18-closed-orders-wid027.md) | Isolated closed_orders slice + Positions Flatten via place/ADR 007 |
| 2026-07-18 | [Close vs Cancel SSOT audit (Closed Orders / flatten)](2026-07-18-close-vs-cancel-ssot-audit.md) | Cancel≠Close; exit_pos/place+ORDERS_GATE; flatten=Nova OS only; history tab read-only |
| 2026-07-18 | [IBKR Gateway paper/live port self-heal](2026-07-18-ibkr-gateway-port-self-heal.md) | Prefer port refuse → try other (4001↔4002), persist mode; orders stay gated |
| 2026-07-18 | [Cancel open-order gate SSOT dispatch (execution + hotkeys)](2026-07-18-cancel-open-order-ssot-dispatch.md) | Yes: working cancel via execute+CANCEL_GATE; UML gap; panel ≠ hotkeys dispatcher |
| 2026-07-18 | [Execution cancel paths + open-order CANCEL_GATE SSOT audit](2026-07-18-execution-cancel-open-order-gate-audit.md) | Open/working cancel via execute+CANCEL_GATE; UML gap; sample mock disables cancel |
| 2026-07-18 | [Hotkeys cancel ownership audit](2026-07-18-hotkeys-cancel-ownership-audit.md) | Cancel SSOT: broker=`execute(cancel)`; hotkeys owns `cancel_symbol` only; panel cancel stays IBKR/widgets |
| 2026-07-18 | [Working Orders panel (Webull WID-026)](2026-07-18-working-orders-panel.md) | Post-place Working Orders panel + column map (WID-026) |
| 2026-07-18 | [Silence Vite HMR flood in client-error logs](2026-07-18-vite-hmr-client-error-flood.md) | Filter @vite/client noise out of /api/client-errors |
| 2026-07-18 | [Rebind shortcuts on the go via TanStack recorder](2026-07-18-rebind-shortcuts-tanstack.md) | Rebind shortcuts on the go via TanStack recorder |
| 2026-07-18 | [Header connection status cluster (API / Gateway / Prices)](2026-07-18-header-connection-status-cluster.md) | Labeled API / Gateway / Prices chips replace ambiguous “Connected” |
| 2026-07-18 | [Ctrl+M shortcuts cheat-sheet peek/pin](2026-07-18-ctrl-m-shortcuts-menu.md) | Ctrl+M shortcuts cheat-sheet peek/pin |
| 2026-07-18 | [Apple-inspired light/dark appearance tokens](2026-07-18-apple-theme-light-dark.md) | Apple-inspired light/dark appearance tokens |
| 2026-07-18 | [Phase G3 Nova Actions + hotkeys specialist](2026-07-18-phase-g3-nova-actions.md) | G3 verified: Map-to-Nova-Action + browser; typed Nova Actions |
| 2026-07-18 | [Agent dreaming](2026-07-18-agent-dreaming.md) | Nova-native light/REM/deep consolidation for `.cursor/agent-memory/` |
| 2026-07-18 | [Task log system](2026-07-18-task-log-system.md) | Durable `knowledge/task-log/` + always-on rule so every job records why |
| 2026-07-18 | [SEC-001–008 remediation](2026-07-18-sec-001-008-remediation.md) | API key guard, config mask, webhook SSRF, optional torch, CORS/Docker/CI |
