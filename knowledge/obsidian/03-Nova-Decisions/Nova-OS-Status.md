# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P10
- State: verified
- Last verified commit: (pending)
- Last updated: 2026-07-15 ~16:30 ET

## Completed this phase

- **P8** — R2 upload/health code (loud when unconfigured); trim still requires verified remote; `docs/r2-archive-setup.md`
- **P9** — replay/ask/evening_review + CLI + ArchiveRewind UI stub + archive APIs
- **P10** — Live-readiness review: **NO-GO for auto_live** (explicit; separate phase required)

## Prior phases

- P0 continuity → P1 events → P2 decide → P3 UX → P4 confirm → P5 auto_paper → P6/P7 local archive — all verified on master

## In progress / uncommitted

- Unrelated HOD/earnings WIP remains in git stash on feature branch

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
