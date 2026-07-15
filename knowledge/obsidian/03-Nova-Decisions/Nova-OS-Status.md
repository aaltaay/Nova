# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P10
- State: verified
- Last verified commit: 171a11a758d89349cfa0ad9ba1519eef57e12b12
- Last updated: 2026-07-15 ~16:30 ET

## Completed this phase

- **P8** — R2 upload/health code (loud when unconfigured); trim still requires verified remote; `docs/r2-archive-setup.md`
- **P9** — replay/ask/evening_review + CLI + ArchiveRewind UI stub + archive APIs
- **P10** — Live-readiness review: **NO-GO for auto_live** (explicit; separate phase required)

## Prior phases

- P0 continuity → P1 events → P2 decide → P3 UX → P4 confirm → P5 auto_paper → P6/P7 local archive — all verified on master

## In progress / uncommitted

- Unrelated HOD/earnings WIP remains in git stash on feature branch
- **Nova OS hardening pass (2026-07-15):** a post-P10 audit found P2–P7 were partial/prototype (unsafe flatten, non-atomic staged approval, mode-receipt split-brain, ambiguous startup recovery, consecutive- vs daily-loss policy). Sections 1–2 (contain-execution, truthful-decisions) landed in commit `52cf76e` — see `CHANGELOG.md`/`PROBLEM_LOG.md` 2026-07-15 "Nova OS hardening". Section 3 (operator UX — unified mode controls, global event-driven attention strip, live browser E2E) landed in commit `8997358` — see `CHANGELOG.md` 2026-07-15 "hardening section 3". Section 4 (archive durability — atomic cold writes, hard-fail on missing/tampered manifests in `upload_day`/`restore_day_to_temp`, new `archive/l2_bridge.py` bridging the pre-existing `l2/db.py` L2 depth/tape recorder into the same checksummed cold-archive + R2 pattern) landed — see `CHANGELOG.md`/`PROBLEM_LOG.md` 2026-07-15 "hardening section 4". Sections 5–6 (no-hindsight replay, phase-status correction) remain in progress; the phase table above still reflects pre-audit claims until `correct-phase-status` finishes. Known follow-up: R2 Bucket Lock (object immutability) still not configured (infra/console change, not code); `l2_bridge`'s verified status is reported in `archive_health()` but not yet folded into its top-level ok/problems gate.

## Crash or blocker

- P8 upload inactive until user adds R2 keys to `.env` (code ready; health shows `configured=false`)

## Verification ledger

- archive + replay + r2 + auto_paper pytest: 33 passed
- npm run build: PASS
- auto_live remains rejected in control_mode

## User action needed

- Optional: create Cloudflare R2 bucket + put keys in local `.env` (see `docs/r2-archive-setup.md`)
- **Do not enable auto_live** without a new approved implementation phase after paper metrics clear

## Phase-close / Next chat starts here

**Nova OS P0–P10 plan map is complete.** Next work is *outside* this plan:
1. Paper shadow days + evening review annealing
2. User R2 setup when ready
3. Separate explicit phase if/when live readiness flips to GO
