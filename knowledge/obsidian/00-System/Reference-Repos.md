# Reference Repos (study catalog)

Study-only index for engines, journals, and skills tooling. **Not vendored into Nova** unless a future phase explicitly adopts a dependency after license review.

**Snapshot date:** 2026-07-15  
**Companion:** [[Skills-Library]] (vendored Cursor skills)

## Study-vs-dependency boundary

| Mode | Meaning |
|------|---------|
| **Study** | Read patterns, UX ideas, APIs, architecture. Do **not** copy large trees into Nova or add as runtime deps without a phase + license check. |
| **Dependency** | Pinned in `requirements.txt` / `package.json` and used by Nova code. Requires explicit phase (e.g. Phase E for vectorbt) and license compatibility. |
| **Skill vendor** | Markdown/agent skills under `.cursor/skills/` — see [[Skills-Library]]. Different from shipping a Python library into the API. |

Nova defaults: IBKR-only execution, single market-data feed, archive honesty, `auto_live` NO-GO. External repos never override those.

---

## Catalog

### nautilus_trader

| Field | Value |
|-------|--------|
| **URL** | https://github.com/nautechsystems/nautilus_trader |
| **Stars (2026-07-15)** | ~24,718 |
| **License** | LGPL-3.0 |
| **Why useful** | Production-grade event-driven trading engine patterns (determinism, adapters, backtest vs live separation). |
| **Boundary** | **Study** for architecture ideas. LGPL has copyleft implications — do **not** silently vendor core into Nova as a dependency without a deliberate legal/product decision. Not a substitute for Nova OS `decide()` / executor ladder. |

### vectorbt

| Field | Value |
|-------|--------|
| **URL** | https://github.com/polakowo/vectorbt |
| **Stars (2026-07-15)** | ~8,322 |
| **License** | Apache-2.0 **with Commons Clause** (see upstream `LICENSE.md`) — restricts selling the software; treat as **non-standard** for productization. |
| **Why useful** | Fast vectorized backtests; aligns with Phase E and vendored VectorBT skills. |
| **Boundary** | **Study now**; candidate **Dependency** only in Phase E after confirming Commons Clause fit for Nova’s use (internal research tool vs redistributed product). Skills under `.cursor/skills/` already teach usage without bundling the library into the repo. |

### TradeNote

| Field | Value |
|-------|--------|
| **URL** | https://github.com/Eleven-Trading/TradeNote |
| **Stars (2026-07-15)** | ~879 |
| **License** | GPL-3.0 |
| **Why useful** | Open-source trading journal UX — tags, recall, consistency workflows relevant to Phase F Reports v2. |
| **Boundary** | **Study** for journal UX. GPL-3.0 copyleft — do **not** vendor as Nova core without accepting GPL obligations. Prefer learning patterns over embedding. |

### deltalytix

| Field | Value |
|-------|--------|
| **URL** | https://github.com/hugodemenez/deltalytix |
| **Stars (2026-07-15)** | ~132 |
| **License** | CC BY-NC 4.0 (non-commercial) — **not** a free-for-commercial-product license. |
| **Why useful** | Modern trading-journal / stats dashboard ideas (AI agents + statistics UI). |
| **Boundary** | **Study / reference-only.** Do **not** copy code into Nova for a commercial product path without license change or permission. UX inspiration for Phase F only. |

### awesome-cursor-skills

| Field | Value |
|-------|--------|
| **URL (plan name)** | https://github.com/chrisboden/awesome-cursor-skills — **404 as of 2026-07-15** |
| **Closest active index** | https://github.com/spencerpauly/awesome-cursor-skills (~572 stars; license not SPDX-classified on GitHub) |
| **Why useful** | Curated index of Cursor/agent skills for discoverability beyond Nova’s vendored set. |
| **Boundary** | **Study / discovery only.** Do not bulk-install skill dumps (especially crypto). Promote candidates into [[Skills-Library]] only after license + Nova-fit review + SHA pin. |

### vercel-labs/skills

| Field | Value |
|-------|--------|
| **URL** | https://github.com/vercel-labs/skills |
| **Stars (2026-07-15)** | ~26,246 |
| **License** | Not SPDX-classified on GitHub API at snapshot (check repo before redistributing tooling) |
| **Why useful** | Canonical `npx skills` CLI + conventions for installing/finding agent skills. |
| **Boundary** | **Tooling** for install/discovery. Nova Phase A used manual copy into `.cursor/skills/` (no symlinks on Windows). Prefer `--copy` / real files if using the CLI later. |

---

## Related Nova notes

- [[Skills-Library]] — vendored skills + guardrails  
- [[Graphify-Knowledge-Graph]] — rebuild after vault edits  
