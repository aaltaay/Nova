# Task log index

Newest first. Full narratives live in sibling `YYYY-MM-DD-*.md` files.

| Date | Entry | One-line summary |
|------|-------|------------------|
| 2026-08-05 | [Doc invariants CI gate](2026-08-05-doc-invariants-ci-gate.md) | Live-doc regex gate + Actions wiring; High stale claims fixed |
| 2026-08-05 | [Retire Railway from live deploy docs](2026-08-05-retire-railway-deploy-docs.md) | Backend local-only; Railway retired from live docs/CI |
| 2026-08-04 | [HOD Momo sort by TIME not emit lag](2026-08-04-hod-momo-time-sort.md) | HOD Momo sort by TIME not emit lag |
| 2026-08-04 | [IBKRPRO up but Nova prereq false login / stuck synchronizing](2026-08-04-ibkr-prereq-false-login.md) | IBKRPRO up but Nova prereq false login / stuck synchronizing |
| 2026-08-03 | [MASTER TEST QTY GATE (force one share)](2026-08-03-force-one-share-qty-gate.md) | IBKR_FORCE_ONE_SHARE clamps place/bracket to 1 share |
| 2026-08-03 | [Level 2 multi-color price tiers](2026-08-03-l2-multicolor-tiers.md) | Classic DAS rainbow L2 tiers (shared hue cycle) |
| 2026-08-03 | [Trading prerequisites gate (no Alpaca as API)](2026-08-03-trading-prerequisites-gate.md) | Trading prerequisites gate (no Alpaca as API) |
| 2026-07-31 | [Sentry usefulness hardening (quiet inbox + ops-once)](2026-07-31-sentry-usefulness-hardening.md) | before_send + bridge WARN + BenignIbkr expand + session_unusable fingerprint; backlog cleaned |
| 2026-07-31 | [IBKR usable-session SoT recovery (core + consumers/ops)](2026-07-31-ibkr-usable-session-sot.md) | Linear 1100/1101/1102 + earn_usable + status.connected=usable; banner/integrity/smoke/daily-start consumers |
| 2026-07-31 | [Fix empty gappers/gainers after ib_async pin (startReq removal)](2026-07-31-fix-empty-gappers-startreq.md) | Typed requests/subscriptions registry adapter + real-import compat guard |
| 2026-07-30 | [IBKR order-truth hardening (10349 / TIF / wedge)](2026-07-30-ibkr-order-truth-hardening.md) | False Cancelled heal; tif=DAY; cancel verify; lag wedged |
| 2026-07-30 | [Webull-style Nova Actions (Buy 1 / Cancel All / long-only percent exits)](2026-07-30-webull-style-nova-actions.md) | Webull-style Nova Actions (Buy 1 / Cancel All / long-only percent exits) |
| 2026-07-30 | [Shared GlobalAppBar status strip on Scanner and Trader](2026-07-30-shared-global-app-bar-status.md) | Shared GlobalAppBar status strip on Scanner and Trader |
| 2026-07-30 | [Morning wedge recurrence fixes](2026-07-30-morning-wedge-recurrence-fixes.md) | Daily bootstrap recycle + completed-orders cooldown + queue logging; OPEN premarket-before-04:00 |
| 2026-07-30 | [Hot Keys Webull-style Settings shell (landing + manager + create)](2026-07-30-hotkeys-webull-settings-shell.md) | Hot Keys Webull-style Settings shell (landing + manager + create) |
| 2026-07-30 | [Integrity banner false warn root causes](2026-07-30-integrity-false-warn-root-causes.md) | Fix false Integrity warns; IBC daily restart; seed retry |
| 2026-07-30 | [HOD News flame column + calculation tooltips](2026-07-30-hod-news-flame-column-tooltips.md) | HOD News flame + header formula tooltips; source-tagged join |
| 2026-07-29 | [Single header row (scanner chrome into GlobalAppBar)](2026-07-29-single-header-row.md) | Single header row (scanner chrome into GlobalAppBar) |
| 2026-07-29 | [HOD dock middle-column only (3-column scanner)](2026-07-29-hod-dock-middle-column.md) | HOD dock middle-column only (3-column scanner) |
| 2026-07-29 | [HOD Momo global AppShell dock](2026-07-29-hod-momo-global-dock.md) | HOD Momo global AppShell dock |
| 2026-07-29 | [Webull-style left scanner rail](2026-07-29-webull-left-scanner-rail.md) | Webull-style left scanner rail |
| 2026-07-29 | [Scanner status chrome above GlobalAppBar](2026-07-29-status-chrome-above-global-bar.md) | Scanner status chrome above GlobalAppBar |
| 2026-07-29 | [Account control next to Settings on GlobalAppBar](2026-07-29-account-next-to-settings.md) | Account control next to Settings on GlobalAppBar |
| 2026-07-29 | [Remove Dashboard tab; Gappers homepage](2026-07-29-remove-dashboard-tab.md) | Remove Dashboard tab; Gappers homepage |
| 2026-07-29 | [Webull-style Settings shell + Trade defaults](2026-07-29-webull-style-settings-shell.md) | Left-rail Settings overlay; Trade > Stocks prefs; FORCE_QTY cleared |
| 2026-07-29 | [Chart pane wedge + live tip repair](2026-07-29-chart-pane-wedge-live-tip.md) | Retry timed-out panes; 1Day/10Sec live tip; slot_wait log |
| 2026-07-29 | [Trader 10-Second chart (4h history + live)](2026-07-29-trader-10sec-chart.md) | 4th pane 10Sec: 14400 S IBKR hist + WS live tip |
| 2026-07-29 | [Chart pipeline Phases 2-4: store, lifecycle, grid](2026-07-29-chart-pipeline-phases-2-4.md) | barsStore, stable LWC, 3-pane grid, hidden-tab pause |
| 2026-07-29 | [Chart bars Phase 1: IBKR TTL cache + batch + warm](2026-07-29-chart-bars-phase1-cache.md) | TTL cache + single-flight + /bars/batch + WS warm |
| 2026-07-29 | [Stock Quote unified widget (stats + L2 + T&S)](2026-07-29-stock-quote-unified-widget.md) | One Stock Quote card owns stats + L2 + T&S in Trader rail |
| 2026-07-29 | [Trader TRADE pane no longer clipped](2026-07-29-trader-trade-pane-clip.md) | Trader TRADE pane no longer clipped |
| 2026-07-29 | [Global single-row app header (Webull-style)](2026-07-29-global-app-bar.md) | Shared AppShell bar: Scanner/Trader nav + Day P&L/Net Liq/BP/Working |
| 2026-07-29 | [Shortcuts menu hold Ctrl+Alt popup](2026-07-29-shortcuts-menu-hold-ctrl.md) | Hold Ctrl+Alt peeks shortcuts menu; Listening accepts modifier chords |
| 2026-07-29 | [Trader tabs + slim Quote Panel](2026-07-29-trader-tabs-slim-quote-panel.md) | L1-only scrollable Quote Panel; Trader max 3 editable L2/T&S tabs |
| 2026-07-29 | [HOD multi-strategy pills stack vertically](2026-07-29-hod-strategy-pills-stack.md) | Stack STRATEGY pills; variable-height virtualizer offsets |
| 2026-07-29 | [HOD strategy config schema v9 repair](2026-07-29-hod-strategy-config-schema-v9.md) | Re-enable 2–9; add Approaching HOD #13; clarify price 0 = disabled |
| 2026-07-29 | [Cursor rules token economy](2026-07-29-cursor-rules-token-economy.md) | Re-scope 8 rules + dedupe AGENTS §12; ~30k→~19k always-on tokens |
| 2026-07-29 | [Quote panel News collapses to one header](2026-07-29-quote-news-collapse.md) | One News container; collapsed shows lead headline only |
| 2026-07-29 | [Approaching HOD alert + side quote panel viewport fit](2026-07-29-approaching-hod-and-quote-panel-fit.md) | Approaching HOD alert + side quote panel viewport fit |
| 2026-07-29 | [Fix cold-Gateway event-loop wedge](2026-07-29-ibkr-cold-start-event-loop-wedge.md) | Fix cold-Gateway event-loop wedge |
| 2026-07-29 | [Remove Gappers Small Cap sub-tab](2026-07-29-remove-gappers-small-cap-tab.md) | Drop All Gaps / Small Cap bar; Gappers shows full list |
| 2026-07-28 | [Trader View unclickable (flex host chain)](2026-07-28-trader-view-unclickable-flex-host.md) | AppErrorBoundary hosts broke Stock View height; clicks hit #root |
| 2026-07-28 | [Phase B waived; Phase K short entry E2E (K0-K4)](2026-07-28-phase-k-short-entry-e2e.md) | B waived; K0-K4 code+UI shipped; K3 human paper days open |
| 2026-07-28 | [Phase K short entry defined in roadmap (not started)](2026-07-28-phase-k-short-entry-defined.md) | K0–K4 scoped: shortability truth, execution gate, paper→live, L2 chip; gated on Phase B |
| 2026-07-28 | [Follow-up ask coaching footer (constitution §5)](2026-07-28-follow-up-ask-footer.md) | §5 footer now requires Better ask + Follow-up ask paragraphs |
| 2026-07-28 | [G8: refresh HOD active set on roster commit](2026-07-28-g8-roster-commit-hod-refresh.md) | G8: refresh HOD active set on roster commit |
| 2026-07-28 | [G9: persist session_high_raised_ts grace clock](2026-07-28-g9-persist-session-high-raised-ts.md) | G9: persist session_high_raised_ts grace clock |
| 2026-07-28 | [G1-G9 HOD capture remediation closeout](2026-07-28-g1-g9-remediation-closeout.md) | All G1-G9 shipped; audit §5b; 1010 pytest + replay parity |
| 2026-07-28 | [G7: Former Momo sub-cap (20 slots)](2026-07-28-g7-former-momo-sub-cap.md) | Cap Former Momo at 20 so live movers keep half the HOD pool |
| 2026-07-28 | [G6: archive enrichment snapshots for replay](2026-07-28-g6-enrichment-snapshots.md) | UPSERT enrichment_snapshots on snap change; replay prefers archive |
| 2026-07-28 | [G8: refresh HOD active set on roster commit](2026-07-28-g8-roster-commit-hod-refresh.md) | Roster commit refreshes HOD pool and wakes L1 reconcile |
| 2026-07-28 | [G9: persist session_high_raised_ts grace clock](2026-07-28-g9-persist-session-high-raised-ts.md) | Highs cache round-trips new-HOD grace clock across restart |
| 2026-07-28 | [G2/G3: market-data type honesty + close-fallback quote quality](2026-07-28-g2-g3-market-data-honesty.md) | reqMarketDataType(1), delayed status/badge, close_fallback + exchange-time stamps |
| 2026-07-28 | [G5: archive HOD L1 decision stream](2026-07-28-g5-archive-l1-decision-stream.md) | Active-set L1 ticks written to archive.l1_ticks after on_trade_update |
| 2026-07-28 | [Fix G1 zombie L1 subs + G4 session errorEvent](2026-07-28-g1-g4-zombie-l1-session-errors.md) | Fix G1 zombie L1 subs + G4 session errorEvent |
| 2026-07-28 | [HOD scanner capture audit + mock replay harness](2026-07-28-hod-scanner-capture-audit.md) | HOD scanner capture audit + mock replay harness |
| 2026-07-24 | [Remove daddy dispatcher; zero-hop specialist routing](2026-07-24-remove-daddy-zero-hop-routing.md) | Deleted daddy; parent now works in-session by default, specialists opt-in-only; reviewed refactoring.guru/loop-library principles |
| 2026-07-24 | [Loud IB Gateway disconnected banner + reconnect warm-up empty state](2026-07-24-ibkr-gateway-login-ux.md) | Loud IB Gateway disconnected banner + reconnect warm-up empty state |
| 2026-07-24 | [End-to-end execution measurement](2026-07-24-end-to-end-execution-measurement.md) | Clock-safe browser/backend stages, bounded fill/slippage evidence, segmented rollups, stale cancel/replace ack fix |
| 2026-07-23 | [Per-operation latency measurement](2026-07-23-per-operation-latency-measurement.md) | Bounded operation metrics; reconnect/lock/boot/attribution fixes; no new broker requests or orders |
| 2026-07-23 | [Block fractional Flatten + hard-fail Error 10243 cancel](2026-07-23-fractional-flatten-error-10243.md) | Block fractional Flatten + hard-fail Error 10243 cancel |
| 2026-07-23 | [AH sticky bridge-error fix + Former Momo watchlist bloat diagnosis](2026-07-23-ah-sticky-bridge-error-and-former-momo-bloat.md) | AH sticky bridge-error fix + Former Momo watchlist bloat diagnosis |
| 2026-07-23 | [Fix HOD active-set stale cache (WLDS lockout)](2026-07-23-fix-hod-active-set-stale-cache.md) | Fix HOD active-set stale cache (WLDS lockout) |
| 2026-07-23 | [ADR 008 persistent scanner stream (shadow) + freeze + table-scoped WS](2026-07-23-adr-008-persistent-scanner-shadow.md) | Persistent IBKR scanner leases in shadow; freeze/rollover; table-scoped WS; cutover flag still off |
| 2026-07-23 | [API_WEDGED dedicated scan pool + auto-heal + app-shell auto-recover](2026-07-23-api-wedged-autoheal-and-app-shell-recovery.md) | Dedicated scan_executor keeps health responsive; session-once auto-restart on WEDGED/DOWN; app-shell boundary auto-reloads once on fatal provider/hook crashes |
| 2026-07-23 | [API/IBKR lifecycle hardening: readiness, cancellation, single supervisor](2026-07-23-api-ibkr-lifecycle-hardening.md) | Explicit IBKR READY state + generation-checked cancellable bridge calls; locked owner-aware dev restart supervisor replaces arbitrary port-killing |
| 2026-07-23 | [HOD scanner external survey + health diagnosis](2026-07-23-hod-scanner-external-survey.md) | Live integrity mute root cause; OSS HOD scanners study-only — surgical fix Nova, no rewrite |
| 2026-07-23 | [Mandatory PROBLEM_LOG for every agent](2026-07-23-mandatory-problem-log.md) | Mandatory PROBLEM_LOG for every agent |
| 2026-07-23 | [IBKR-only scanner discovery lock](2026-07-23-ibkr-only-scanner-discovery.md) | IBKR-only scanner discovery lock |
| 2026-07-23 | [Daily auto-start for Gateway + Nova API/UI](2026-07-23-nova-daily-autostart.md) | Daily auto-start for Gateway + Nova API/UI |
| 2026-07-22 | [Quiet Sentry IBKR/chart dispose noise](2026-07-22-sentry-ibkr-noise-filters.md) | Quiet Sentry IBKR/chart dispose noise |
| 2026-07-22 | [Vitest act() environment fix](2026-07-22-vitest-act-environment-fix.md) | Set IS_REACT_ACT_ENVIRONMENT via Vitest setupFiles; restores React 19 act safety net |
| 2026-07-22 | [Warm completed orders + Orders Today badge/empty honesty](2026-07-22-orders-today-completed-orders.md) | Warm completed orders + Orders Today badge/empty honesty |
| 2026-07-22 | [Closed Orders Time Filled column](2026-07-22-closed-orders-time-filled-column.md) | Closed Orders Time Filled column |
| 2026-07-21 | [HOD Momo stable rows + virtualized table](2026-07-21-hod-momo-stable-rows-virtualization.md) | Rows pinned to first-catch time/position instead of re-stamping on re-fire; table switched from unbounded batch-append to fixed-window virtualization |
| 2026-07-21 | [Drop misleading paper-by-default from IBKR order disclosure](2026-07-21-ibkr-order-disclosure-copy.md) | Static IBKR disclosure no longer says paper by default next to LIVE confirms |
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
