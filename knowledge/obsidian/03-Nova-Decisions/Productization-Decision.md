# Productization Decision (Phase J)

> **Date:** 2026-07-15  
> **Status:** DECIDED — local-first single-operator  
> **Canonical roadmap:** [[Nova-Roadmap-Status]]  
> **Related:** [[Nova-OS-Live-Readiness-Review]], constitution invariant #7 (IBKR execution gate)

## Recommendation

**Stay local-first / single-operator for the foreseeable product path.** Do **not** build multi-tenant SaaS, hosted billing, or cloud IB Gateway in the near-term Master Roadmap.

## Why

| Factor | Implication |
|--------|-------------|
| **IB Gateway is local** | Live/paper API ports bind on the operator machine (or a dedicated always-on PC). Casual cloud hosting of Gateway is fragile, ToS-sensitive, and operationally heavy (Phase P). |
| **Secrets & execution** | Alpaca keys, R2 tokens, Discord/Telegram secrets, and IBKR credentials must stay in local `.env` — not in a shared multi-tenant control plane. |
| **Nova OS audit ladder** | `signal` / `confirm` / `auto_paper` + append-only receipts are built for one accountable operator, not delegated cloud agents. |
| **`auto_live` NO-GO** | Live money remains rejected until a separate approved phase after paper evidence — SaaS would amplify unlock risk. |
| **Differentiation already local** | IBKR-primary single feed, modular workstation, archive replay — product value is the desktop/ops loop, not a hosted scanner SaaS. |

## What stays local

- FastAPI + Vite/Electron desktop
- IB Gateway (paper now; live only after future unlock)
- Journal / archive SQLite + optional personal R2 bucket
- Alert channel secrets (Discord / Telegram / webhooks)
- Control-mode arming and flatten drills

## What SaaS would require (explicitly deferred)

- Auth, tenancy, billing, and remote secret vaults
- Remote or vendor-hosted Gateway (Phase P) with a constitution amendment discussion
- Multi-broker execution (Phase O) — research-only until constitution change
- Community / shared setups (Phase Q)

**Do not start those tracks** until this decision is revisited in writing.

## Revisit triggers

Re-open this note only if **all** are true:

1. Phase B ≥5 shadow days + Phase I evidence still NO-GO or GO with user approval for next steps
2. Operator explicitly wants multi-user or remote access
3. A written plan for Gateway hosting + secret isolation exists (not “just put it on a VPS”)

## Exit (Phase J)

- [x] Written decision: **local-first single-operator**
- [x] SaaS / cloud Gateway deferred to K–Z parking lot
- [x] No code change to live gates as part of this phase
