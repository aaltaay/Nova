# 2026-07-23 — HOD scanner health diagnosis + external reuse survey

- **Status:** completed
- **Agents:** hod-momo
- **Domain:** hod-momo | market-feed (adjacent)
- **Related:** `PROBLEM_LOG.md` §2026-07-23 HOD alerts muted by scanner-bridge TimeoutError · `IBKR-Scanner-HOD-Architecture.md` · `.cursor/agent-memory/hod-momo-memory.md`

## Task

Investigation only: why Nova HOD Momo feels broken, and whether open-source / external HOD–momentum scanners are ready to repurpose.

## Goal

Concrete live evidence of Nova failure modes; 3–7 external candidates with reuse vs study-only vs skip; a short roadmap; rewrite vs surgical verdict.

## Why it mattered

User asked whether to abandon Nova’s HOD path for something “ready online.” Wrong answer = either a full rewrite that violates IBKR-only / single-feed invariants, or continued silent mute from a mis-scoped integrity gate.

## What we changed

- No product code.
- Prepended PROBLEM_LOG diagnosis for `integrity_fail_suppress` ↔ scanner-bridge TimeoutError coupling.
- This task-log entry + INDEX row; hod-momo memory run-log update.

## How it works now (Nova HOD — mental model)

1. **Membership:** IBKR `reqScannerData` seeds (volume/gainers/belowPrice) → watch universe ≫ active pool.
2. **Prices / HOD truth:** bounded `reqMktData` L1 (+ tick-6 day high + hist bar seed) → `on_trade_update` → strategy gates → 10s consolidation → UI.
3. **Integrity:** merged HOD + scanner report. If merge status is `fail`, **all** HOD strategy passes are suppressed (`integrity_fail_suppress`) even when HOD L1 is green.
4. **Warrior / Webull:** research-only parity inputs — never feed alert engine.

## Live evidence (2026-07-23 ~11:00 ET)

| Check | Result |
|-------|--------|
| IBKR `/api/ibkr/status` | `connected=true`, live:4001 |
| `hod_momo_session_gate --profile integrity_only` | **FAIL** exit 2 |
| Fail driver | `scanner_ibkr_bridge`: `gainers: TimeoutError` (while gainers cache still 50 rows age≈0s) |
| HOD L1 | pass — trades flowing, active q/e p95≈0.75s |
| Active set | 40/40; uncovered≈535 = capacity design |
| Soft WARNs | `hod_surge_after_seed` (10), coverage 98% warn floor |
| Counters | `integrity_fail_suppress`≈6418; Squeeze fired≈5; Running Up fired≈23; `alerts_today`≈78 |
| Recent alerts | e.g. VIVK Running Up / Squeeze — feed not dead, but heavily gated |

Known open ledger (memory, not re-litigated): timing_definition (SDOT/PN/TRT), capacity_expected (BTMD-class), Error 10089 delayed MD on some names, Former Momo intentionally OFF.

## External candidates (reuse verdict)

| Candidate | License | Feed | Verdict | Why |
|-----------|---------|------|---------|-----|
| [Jayanth7416/ross-cameron-stock-scanner](https://github.com/Jayanth7416/ross-cameron-stock-scanner) | none listed | Yahoo + scraped stockanalysis | **study-only** | Warrior-inspired 5-pillar / HOD filter UI; no IBKR; scrape TOS risk |
| [hybornconcept/stockscreener](https://github.com/hybornconcept/stockscreener) | none listed | yfinance Streamlit | **study-only** | Explicit Warrior price/Δ%/RVOL thresholds; batch EOD-ish, not L1 HOD truth |
| [9600dev/mmr](https://github.com/9600dev/mmr) | NOASSERTION | Massive/Polygon primary + IB fallback | **study-only** (IB scan CLI) | Mature IB scanner wrappers; US path is Polygon — violates single-feed if copied |
| [imterence/ibkr_scanner](https://github.com/imterence/ibkr_scanner) | NOASSERTION | IBKR + auto-trader | **study-only** | Momentum scoring on IB; ships auto-exec — **do not** port trader; small / unlicensed clarity |
| [songzhiyuan98/KLineLens](https://github.com/songzhiyuan98/KLineLens) ENGINE_SPEC | MIT | pluggable | **study-only** | Clean RVOL + optional TOD-RVOL + breakout FSM docs — formula inspiration only |
| [VladPetrariu/Qullamaggie-breakout-scanner](https://github.com/VladPetrariu/Qullamaggie-breakout-scanner) | MIT | free EOD/daily | **skip** (HOD) | Pre-market swing breakout, not intraday new-HOD alerts |
| [pkjmesra/PKScreener](https://github.com/pkjmesra/PKScreener) | MIT | NSE India focus | **skip** | Wrong market / session model |
| [ShayKedem/swing-bot](https://github.com/ShayKedem/swing-bot) | none listed | IBKR VCP swing | **skip** | Multi-day pre-breakout, not day-trade HOD |
| Warrior Day Trade Dash | proprietary | Warrior | **research-only** | Parity gold standard; never ingest into Nova engine |

**No candidate is drop-in reusable** under Nova invariants (IBKR-only discovery/prices, no silent Alpaca/Yahoo price path, `auto_live` NO-GO, no Warrior feed into alerts).

## Why this approach

- Survey before rewrite: OSS “HOD” tools almost all assume Yahoo/Polygon/scrapers or daily bars — they would regress Nova’s shipped tick-6 + bar seed HOD truth.
- Diagnosis before features: live counters prove mute is often **integrity merge**, not missing gates.
- Rejected: forking ross-cameron / hybornconcept as Nova’s scanner — wrong feed + license/TOS + no L1 capacity model.

## Verification

- `py -3 tools/hod_momo_session_gate.py --profile integrity_only` → FAIL (bridge TimeoutError)
- `GET /api/integrity`, `/api/ibkr/status`, `/api/hod-momo/debug/counters`, `/api/hod-momo/alerts?limit=8`
- GitHub `gh api repos/...` for license/stars; web survey of scanner repos

## Follow-ups

1. **Surgical fix first:** scope HOD suppress to hod_momo integrity fail (or IBKR disconnect), not scanner-bridge flaps; demote fresh-cache TimeoutError to warn.
2. **Parity loop:** warrior refresh + observe once gate is armable; classify warrior_only with existing buckets.
3. **Study-only:** skim KLineLens RVOL TOD + Warrior-inspired filter tables — adapt constants only inside `constants_hod_momo.py` / filters, never swap data plane.
4. **Do not** rewrite HOD on Yahoo/Polygon/scraper stacks.

## Keywords

HOD Momo, integrity_fail_suppress, external scanner survey, Warrior research-only, IBKR-only, rewrite vs surgical, RVOL, ross-cameron-stock-scanner, mmr, KLineLens
