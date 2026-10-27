# Nova Roadmap Status

> **Canonical product roadmap ledger** for the Master Roadmap A-Z. Short by design -- closed phases, verification baselines, and older History rows live in [[Nova-Roadmap-Archive]].
> **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc`
> **Canvas (project homepage):** `canvases/nova-home.canvas.tsx`
> **Nova OS engine status (retired, ADR 025):** [[Nova-OS-Status]]
> **Retired readiness review (Phase I):** [[Nova-OS-Live-Readiness-Review]] · **Productization (Phase J):** [[Productization-Decision]] · **Idea bank:** [[Nova-Expansion-Ideas]]

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## Current position

- **Product NEXT:** **Phase L -- strategy proof (bot trading plan)**, `[~]` S6 built -- the setup scanner (Watchlist > Setups, ADR 022) watches the first pullback with the live Level 2 / tape as the gate and scores every armed setup, and since 2026-09-24 the L2 first-pullback bot trades its go triggers itself on Paper (ADR 030; research never grants manual Live permission and bots never trade Live); next is its read-out on Paper sessions (§2g) beside the operator's ten-day hand run, and S5 the rolling-universe screen offline (decision 2026-09-22 night): seven bar-level readings of small-cap setups have now failed gate 1 on one honest harness (ORB, Gap and Go, the ORB on seconds, the first pullback, the flat-top breakout, red-to-green; A4 was large-cap). The private catalogue is done on F:; the chosen setup is the first pullback -- traded by hand on Paper as the operator's material prescribes, and watched by the bot with the live Level 2 / tape as the gate. S7 (§2h) closed day-level only on its 20-day pilot (52% of trades pinned, 85% of days reconciled; no twelve-month ledger exists). **Next question (operator, 2026-10-27, §2j): Claude's own Paper seat (ADR 068)** -- a forward trial of a model's live judgment on Paper, information only. Halts last, A5 parked. Plan, results and done-criteria in [[Bot-Trading-Plan]].
- **Phase K (short entry):** `[x]` short-sale build shipped (ADR 048/049); mandatory K3 Paper proof retired by operator decision 2026-10-13 (#791). Explicit Live opt-ins and order safety remain.
- **`auto_live`:** **NO-GO** -- rejected in `backend/nova_os/control_mode.py`. Do not enable or implement.
- **Phase B (paper shadow ops):** **WAIVED** by user 2026-07-28 (0 evidence rows; not `[x]`). Do not block work on ≥5 shadow days.
- **Phase C (durable archive):** `[~]` PARTIAL -- remainder is optional operator work (see below).
- **Phase I (live readiness):** **RETIRED** by operator decision 2026-10-13 (#791). Research informs the human, never trading permission.
- **Reliability track (WS0-WS7):** shipped 2026-08-18; only **WS1 proof** is open (first unattended 03:55 ET run).
- **Closed:** Phases A, D, E, F, G, G2, G3, H, J · Nova OS P0-P10 · Maintenance Phases 0-13 -> [[Nova-Roadmap-Archive]]
- **Last verified commit:** `aad9bf9` (architecture close remediation Phase 7). Tip SHA: `git rev-parse --short HEAD`.
- **Last updated:** 2026-10-27 (Phase L's next research question chosen: Claude's own Paper seat, ADR 068; S7 pilot result recorded)

## Exact next action (human)

1. **Phase L research:** chosen 2026-10-27 -- Claude's own Paper seat (ADR 068, [[Bot-Trading-Plan]] §2j); the S7 pilot result is recorded in §2h. Turn the seat on during Paper sessions; the S6 scoreboard keeps counting alongside (11 of the 50 go setups its read-out needs, 2026-10-27). Done when the seat's read-out and its limitations are recorded in §2j. Information for the operator only, never a Live readiness verdict.
2. **Reliability WS1:** configure a Discord/Telegram channel in Settings; run `.\scripts\Install-NovaDailyTask.ps1` once; leave the PC on overnight (wake timers). The first 03:55 ET line in `backend/logs/morning-check.log` closes the Jul 30 PROBLEM_LOG entry.
3. **Optional Phase C remainder:** Cloudflare Bucket Lock + R2 token rotation + cold `walk_day`.
4. **Hard ban:** no `auto_live` or Live bot. Manual Live orders keep explicit operator opt-ins/PIN, broker eligibility and common order safety; no K3 sign-off or research verdict is required.

## Open phases

### Phase L -- Strategy proof (bot trading plan) -- `[~]` NEXT

**User direction (2026-09-22):** the operator wants a bot that trades a proven strategy, and asked for the stale K3 step to stop being offered. Plan, decisions, stage done-criteria and reference numbers live in [[Bot-Trading-Plan]] (SSOT for this phase).

- **L0 pick one strategy** `[x]` -- Decision A = A1 (5-minute ORB on stocks in play, long-only first; SPY swing baseline alongside; Gap and Go second), 2026-09-22
- **L1 get the data** `[x]` -- Decision B = B1 (Massive Stocks Starter, one month): 1,255 days of minute + day flat files 2021-09-21..2026-09-21, tickers (active + delisted), splits, dividends, ticker details, news archive, short data, one-second bars for selected symbol-days, all on `F:\Nova\data\massive`; DuckDB store built by `research/orb/`
- **L2 backtest** `[x]` A1, A2, A4, S1, P1-P3 / A5 parked -- own DuckDB + numpy harness (vectorbt not needed), IBKR costs + slippage, no lookahead; ORB long-only on minute bars: 3,919 trades, PF 1.20, 26% CAGR at $0.01 slippage; the same ORB replayed on one-second bars (S1): 3,384 trades, PF 0.97, -4% CAGR; Gap and Go mechanical: 778 trades, PF 1.00; large-cap RSI2 mean reversion: 1,223 trades, PF 1.02, 1.75% CAGR; first pullback P1: 589 trades, PF 0.54; flat-top P2: 63 trades, PF 0.20; red-to-green P3: 398 trades, PF 0.58
- **L3 try to break it** `[x]` A1, A2, A4, S1 / A5 parked -- ORB fails the 2x-cost test (PF 1.00) and keeps 123% of its profit in the 10 best trades; Gap and Go fails three of four; A4 fails three of four (2024 carries it, PF 1.00 at 2x costs); A4b mega-cap cell survives 2x costs (PF 1.17) but is an in-sample universe pick; S1 fails three of four (negative at 1c, PF 0.83 at 2c, profit in ~10 trades -- 82% of trades stop on a one-second low, half inside 60 s: the published stop is 0.4% of price); P1-P3 are negative in every ladder cell and at zero cost (the bar shape is not the edge). Kill criteria and full tables in [[Bot-Trading-Plan]] §2b-§2f
- **L4 Paper research** `[~]` -- optional observations for the operator; no required sample or expectancy agreement grants trading permission. Current question: Claude's own Paper seat (ADR 068, [[Bot-Trading-Plan]] §2j, chosen 2026-10-27).
- **L5** **RETIRED as readiness permission** 2026-10-13; research does not authorize Live bots or demand a Live probe.

### Phase K -- Short entry -- `[x]` build shipped, readiness workflow retired

ADR 048/049 shipped the common short check, Paper/Sim short ledgers and bot support, manual Live controls,
short-entry cutoff, day cover and alarms. On 2026-10-13 the operator retired K3 mandatory Paper days,
drills/sign-off and the Live short proof (#791). Historical observations remain evidence, not permission.
No funding, account reset, Paper sample, Gateway interruption or Live probe is an outstanding roadmap task.

Short entry stays explicit per order. Live requires the operator-controlled Live opt-ins and PIN arming;
broker/account eligibility, required stop, hours, halt, borrow, SSR, margin/cushion and protective-close rules
remain. Bots remain Paper/Sim only and `auto_live` remains NO-GO. Research verdicts never lock Strategy On.

### Phase C -- Durable archive -- `[~]` PARTIAL (optional operator work)

Done: R2 keys + connectivity, `ARCHIVE_MAINTENANCE_ENABLED`, L2 failures folded into `archive_health`, Bucket Lock + rotation steps documented in `docs/r2-archive-setup.md`. Hot `bars_1m` backfilled from tape (331 bars, 2026-07-17).

- [ ] R2 Bucket Lock enabled in the Cloudflare console (operator)
- [ ] Temporary/test R2 token rotated (operator)
- [ ] Upload/restore on a **real** compacted production day, then `walk_day` on that cold day

Do not fake Phase C `[x]`.

### Phase I -- Live-readiness workflow -- RETIRED (operator decision 2026-10-13)

There is no GO/NO-GO scorecard that decides trading eligibility and no required reviewed-day sample.
[[Nova-OS-Live-Readiness-Review]] records this retirement. The human judges research seriousness; explicit
operator arming and broker/account/order safety remain. `auto_live` and Live bots remain prohibited.

### Reliability track -- problem-root elimination (2026-08-18)

Closes the five PROBLEM_LOG root patterns. Not a Master Roadmap letter phase; product NEXT stays Phase L.

| WS | Status | Closes |
|----|--------|--------|
| 0 Ledger | `[x]` | This section |
| 1 Morning autopilot | `[~]` | Tooling shipped. Proof = first real 03:55 ET line in `backend/logs/morning-check.log`; Jul 30 PROBLEM_LOG stays OPEN until then |
| 2 IB-loop purity guard | `[x]` | `tools/maintainer_lib/ib_loop.py` + CI `--fail-on-kind ib_loop_sync_io` |
| 3 Fail-loud REST | `[x]` | `table_state` / `roster_ts` / `feed_error` on gappers/movers/AH |
| 4 Persisted-state rule | `[x]` | `.cursor/rules/persisted-state.mdc` + corrupt channels ERROR log |
| 5 SSOT audit | `[x]` | Remaining dual-read is gated (`chart_bars.py` Alpaca path); qty SSOT is `ib.positions()`; Orders Today is a ledger overlay |
| 6 Test isolation | `[x]` | conftest import-time `NOVA_CACHE_DIR` + paper Gateway pin |
| 7 Blast-radius verification | `[x]` | Table in `verification-before-completion.mdc` |

### Phases M-Z -- `[~]` DEFERRED (parking lot)

L is promoted above (strategy proof). Still parked: conversational scans, Holly-like coach, L2 scrubber, SMS/email, multi-broker, cloud Gateway, community, native mobile, CI expansion, mission canvas, reserved U-Z. **Not scheduled** until explicitly promoted.

## Crash or blocker

- **Phase L:** nothing blocked; no bar-level rule is alive on the store (seven screens failed); the next evidence is live -- the setup scanner's scoreboard on Paper sessions and the operator's ten-day hand run -- plus S5 offline; S7 closed day-level only (§2h); the chosen next question is Claude's own Paper seat (§2j, ADR 068). Halts last (operator).
- **Phase K:** build shipped; K3 required proof is retired, not a blocker.
- **Phase B:** WAIVED (2026-07-28) -- not a blocker.
- **Phase C remainder:** needs Cloudflare console work + a fresh session compact/walk (optional).
- **Phase I:** readiness workflow and verdict retired; the operator interprets measurements.
- **`auto_live`:** permanent NO-GO in this roadmap window.

## History (append-only)

Newest first. Append here; do not rewrite prior rows. Rows before 2026-07-28 are in [[Nova-Roadmap-Archive]].

| Date | What | Commit |
|------|------|--------|
| 2026-10-27 | Phase L research question chosen by the operator: Claude's own Paper seat (ADR 068, `Bot-Trading-Plan.md` §2j) -- a forward trial of a model's live judgment on Paper within ADR 068's limits, with its limitations stated before any result. S7 pilot result recorded (§2h): day-level only, 52% of trades pinned and 85% of days reconciled; no twelve-month ledger is possible and no rule was registered. Information only; `auto_live` NO-GO. | (this commit) |
| 2026-10-13 | Operator retires machine readiness permission (#791): K3 Paper days/drills, Phase I scorecard and Live short proof removed; research remains information and never locks Strategy On. Explicit Live opt-ins/PIN, broker/account/order safety and Live bot ban remain. | (this commit) |
| 2026-10-11 | S7 pre-registered (`Bot-Trading-Plan.md` §2h): every reading so far tested what the operator's material teaches, none what its author trades. A 20-day pilot on the desk PC checks whether the private video archive yields a verified ledger (80% of trades pinned to a print, 80% of days reconciled to the stated P&L) before any twelve-month extraction; the five questions are fixed first. Material and ledger stay on F:. `auto_live` NO-GO. | (this commit) |
| 2026-09-23 | Nova OS retired (ADR 025, #481 option a): the verdict, the `signal` / `confirm` / `auto_paper` ladder, the staged queue, the Phase D executor and the decision replay are removed; Watchlist is Watchlist / Setups / Journal / Backtest. The kill switch moves to `backend/kill_switch/` with a card on the Bots page. The bot ladder (ADR 016) is the one automation path. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | S6 built: the setup scanner (ADR 022). One live first-pullback scanner on the HOD Momo names (Watching, Leg up, Armed, Near, Triggered, Failed; P1 rules, 94.9% parity with the research harness) replaces the old setups stream and the Signals sub-tab; its tape gate reads the Level 2 / time and sales the desk holds (go / wait / veto / blind, no new IBKR line); near + go raises an Eyes proposal -- ping, alert card, staged ticket, never a place; every armed setup is scored in `setups.db`. Read-out pre-registered in `Bot-Trading-Plan.md` §2g. The Phase D executor no longer receives signals. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | P1 / P2 / P3: the first pullback, the flat-top breakout and red-to-green as minute-bar rules on the Five Pillars universe after 09:30 -- not passed, negative in every ladder cell and at zero cost (`research/momentum/`). The private catalogue of the operator's material is done on F: (S4). Decision: master the first pullback -- by hand on Paper as prescribed (one trade a day, 20c / 20c, 07:00-10:00), and with the bot in Eyes mode gated by the live Level 2 / tape (S6); S5 rolling-universe screen offline. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | S1: the ORB replayed on one-second bars is not passed (PF 0.97 at 1c, 0.83 at 2c; 82% of trades stop on a one-second low, half inside 60 s -- the published 10%-ATR stop is 0.4% of a $35 median entry, and §2b's minute-bar result was the entry-bar rule hiding intrabar stop-outs). S2 dropped; S3 halts shelved to last (operator). Next S4: catalogue every setup in the operator's private material, off-repo on F:, then choose one to master together; the material stays private, the chosen strategy may be recorded in the plan. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | Operator direction: the bots are for small caps. A5 (SPY swing) parked unrun; the small-cap track of `Bot-Trading-Plan.md` §2e replaces it -- S1 ORB on one-second bars, S2 ORB bot pack on Paper to measure real slippage, S3 halt-resume and VWAP-reclaim pre-registered. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | Gate 1 for A4 large-cap daily mean reversion (split-adjusted daily bars for every US stock, RSI2 < 10 above the 200-day, 5 names, 10-day hold): PF 1.02, 1.75% CAGR, 2024 carries it, PF 1.00 at 2x costs -- not promoted. A4b ($200M+ ADV mega-caps) is the first cell of any candidate to survive doubled costs (PF 1.17, 11% CAGR) but is in sample; recorded, not promoted. A5 SPY swing rules pre-registered as the fourth candidate; a paper stage would need a daily-bar bot pack. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | Gate 1 for A2 Gap and Go, mechanical Five Pillars + pre-market-high break on the same store with the news archive as the catalyst pillar: PF 1.00 and 0.4% CAGR on 778 trades without the survivor-biased float pillar, fails three of four kill tests -- not promoted. Reference dump complete (dividends, details, news, short data, one-second bars), nothing refused; the Massive plan may be cancelled. A4 large-cap daily mean reversion pre-registered as the third candidate. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | Phase L1 complete (five years of minute bars + reference on F:) and gate 1 run for A1: the published ORB rule reproduces the paper's shape but fails the pre-registered 2x-cost test and rests on ~10 trades -- not promoted to paper. Harness `research/orb/` (DuckDB + numpy, honest fills, IBKR costs). SPY swing baseline reproduced its source. Next candidate A2 Gap and Go. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | Phase L0 decided: A1 (5-min ORB, long-only first) + B1 (Massive minute + day flat files, one month). L1 download running to F:. `auto_live` NO-GO. | (this commit) |
| 2026-09-22 | Phase K PARKED (operator: K3 is stale against ADR 020 and no longer wanted as the next step). Phase L -- strategy proof -- promoted from the parking lot as product NEXT; plan in `Bot-Trading-Plan.md`. No gate changed. `auto_live` NO-GO. | (this commit) |
| 2026-09-16 | K4 ticket UI: Direction Long/Short removed. Side is Buy/Sell/Short on Margin (Buy/Sell on Cash) from IBKR AccountType. `short_entry` unchanged. `auto_live` NO-GO. | (this commit) |
| 2026-09-11 | Public source home is `aaltaay/Nova`. Marketing CTA retargeted. `Nova-public` is a private archive. Phase NEXT unchanged (K3). `auto_live` NO-GO. | (this commit) |
| 2026-09-08 | Roadmap note trimmed to a live status page; closed phases, verification baselines, maintenance track, and pre-2026-07-28 History moved verbatim to [[Nova-Roadmap-Archive]]. Task narratives now default to PR bodies. No phase state changed; `auto_live` NO-GO. | (this commit) |
| 2026-08-31 | Public domain `nova.altaystudio.com` is a static marketing page (`site/`), not the hosted scanner. CTA is Nova-public. Phase J local-first. `auto_live` NO-GO. | (that commit) |
| 2026-08-18 | Reliability track WS0-WS7: morning check + system-event alerts, fail-loud scanner REST, pytest cache isolation, IB-loop purity CI gate, blast-radius + persisted-state rules. WS1 proof still needs first unattended 03:55 ET run. `auto_live` NO-GO. | (that commit) |
| 2026-07-28 | Phase B WAIVED + Phase K E2E ship: ADR 009, shortability module, `IBKR_SHORT_ENABLED` + `short_entry` gates, flatten cover, Shortability chip + Long/Short ticket. K3 human paper short days still open. `auto_live` NO-GO. | `125f3ce` |
