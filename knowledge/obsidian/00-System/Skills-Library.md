# Skills Library (Nova Master Roadmap Phase A)

Catalog of **vendored** Cursor agent skills under `.cursor/skills/`. Companion study catalog (not vendored): [[Reference-Repos]].

**Installed:** 2026-07-15  
**Pin file:** `.cursor/skills/SOURCE-PINS.txt`  
**Steward:** `backtester` owns the VectorBT cluster (`backtest`, `optimize`, `strategy-compare`, `vectorbt-expert`, `backtesting-frameworks`); `security` owns `llm-trading-agent-security`. See [[Agent-Fleet-Map]].

## Nova guardrails (applies to every skill below)

These skills **advise research and offline backtesting only**. They must **never**:

- Bypass Nova OS control-mode gates (`signal` / `confirm` / `auto_paper`) or enable / implement `auto_live`
- Place orders outside the IBKR execution gate (`backend/ibkr/` + constitution invariant #7)
- Mix Alpaca market data into quote/chart/scanner/L2 when discovery is `ibkr` (single-market-data-feed rule)
- Treat skill-generated scripts as production Nova trading code without a dedicated phase (Phase E owns backtest product)
- Execute third-party skill bootstrap scripts (`setup`, crypto wallet tooling, Solana dumps) as part of Nova ops

If a skill’s copy conflicts with Nova rules, **Nova constitution + `.cursor/rules/` win**.

---

## Vendored skills

### backtest

| Field | Value |
|-------|--------|
| **Purpose** | Generate a complete VectorBT backtest script (data → signals → stats → plots) for a named strategy/symbol. |
| **Triggers** | User asks to “backtest X on Y”, create a VectorBT script, or run a quick strategy backtest offline. |
| **When NOT to use** | Live trading, paper order placement, scanner/quote feed work, or Phase B shadow ops. Do not use to bootstrap OpenAlgo/crypto env in the Nova repo. |
| **Source** | https://github.com/marketcalls/vectorbt-backtesting-skills |
| **Pinned SHA** | `05d9e8b12fa408f1373c6b79620f8a5473fb874c` |
| **Local path** | `.cursor/skills/backtest/` |
| **License** | MIT (declared in upstream README; no LICENSE file in upstream — see `LICENSE-NOTE.txt`) |
| **Safety notes** | Research/backtest only. Prefer US/yfinance or Nova archive data for Nova work; ignore crypto/CCXT paths unless explicitly researching. Never bypass IBKR-only execution or `auto_live` NO-GO. |

### optimize

| Field | Value |
|-------|--------|
| **Purpose** | Parameter grid/search optimization with VectorBT heatmaps and best-param reporting. |
| **Triggers** | “Optimize parameters”, “grid search”, “heatmap of lookbacks”, walk-style param sweeps offline. |
| **When NOT to use** | Fitting params on live tape; promoting optimized params straight into `auto_paper` without review; any order path. |
| **Source** | https://github.com/marketcalls/vectorbt-backtesting-skills |
| **Pinned SHA** | `05d9e8b12fa408f1373c6b79620f8a5473fb874c` |
| **Local path** | `.cursor/skills/optimize/` |
| **License** | MIT (README; `LICENSE-NOTE.txt`) |
| **Safety notes** | Overfitting risk — pair with `backtesting-frameworks` bias guidance. Research only; no Nova OS gate bypass. |

### strategy-compare

| Field | Value |
|-------|--------|
| **Purpose** | Side-by-side VectorBT comparison of strategies or long/short/both directions on one symbol. |
| **Triggers** | “Compare EMA vs RSI vs Supertrend”, “long vs short on SYMBOL”. |
| **When NOT to use** | Choosing live symbols for the scanner; ranking gappers; anything that implies live execution. |
| **Source** | https://github.com/marketcalls/vectorbt-backtesting-skills |
| **Pinned SHA** | `05d9e8b12fa408f1373c6b79620f8a5473fb874c` |
| **Local path** | `.cursor/skills/strategy-compare/` |
| **License** | MIT (README; `LICENSE-NOTE.txt`) |
| **Safety notes** | Offline comparison only. Does not change discovery provider or place IBKR orders. |

### vectorbt-expert

| Field | Value |
|-------|--------|
| **Purpose** | Knowledge hub for VectorBT patterns (fees, indicators, walk-forward, pitfalls, tearsheets). Auto-loaded reference for the other VectorBT skills. |
| **Triggers** | VectorBT / equity curve / drawdown / openalgo.ta / backtest architecture questions. |
| **When NOT to use** | As a crypto trading skill dump; as authority over Nova feed/execution rules; as a reason to install CCXT into Nova production. |
| **Source** | https://github.com/marketcalls/vectorbt-backtesting-skills |
| **Pinned SHA** | `05d9e8b12fa408f1373c6b79620f8a5473fb874c` |
| **Local path** | `.cursor/skills/vectorbt-expert/` (+ `rules/`, `rules/assets/`) |
| **License** | MIT (README; `LICENSE-NOTE.txt`) |
| **Safety notes** | Includes `crypto-market-costs.md` as fee reference — **do not** treat that as a green light for crypto trading in Nova. Upstream defaults lean Indian markets/OpenAlgo; for Nova Phase E prefer archive-driven US equity paths. Never contradict single-feed / IBKR execution / `auto_live` NO-GO. |

### backtesting-frameworks

| Field | Value |
|-------|--------|
| **Purpose** | Framework-agnostic guidance: look-ahead/survivorship bias, costs, walk-forward, structure of a trustworthy backtest. |
| **Triggers** | Designing Nova `backend/backtest/` (Phase E), reviewing bias, choosing engine patterns. |
| **When NOT to use** | As a substitute for Nova archive honesty (no-hindsight replay); as permission to auto-trade from backtest results. |
| **Source** | https://github.com/wshobson/agents (`plugins/quantitative-trading/skills/backtesting-frameworks`) |
| **Pinned SHA** | `b6af3711058190e4b5c5274b9758498fe626ec5a` |
| **Local path** | `.cursor/skills/backtesting-frameworks/` (+ `references/details.md`) |
| **License** | MIT (upstream `LICENSE` vendored beside skill) |
| **Safety notes** | Complements VectorBT skills with bias hygiene. Research/design only; Nova OS gates remain authoritative. |

### llm-trading-agent-security

| Field | Value |
|-------|--------|
| **Purpose** | Security patterns for LLM agents with transaction/wallet authority: injection, spend limits, simulation, circuit breakers, key handling. |
| **Triggers** | Reviewing alert→exec paths, hardening tool permissions, threat-modeling autonomous trading agents (Phases D–I). |
| **When NOT to use** | As a crypto/Solana wallet skill; as a recipe to give the agent live signing keys; to justify `auto_live`. |
| **Source** | https://github.com/affaan-m/everything-claude-code (`skills/llm-trading-agent-security`) |
| **Pinned SHA** | `ed387446052dfbc6b52de149406b70efa65edc59` |
| **Local path** | `.cursor/skills/llm-trading-agent-security/` |
| **License** | MIT (upstream `LICENSE` vendored beside skill) |
| **Safety notes** | Upstream examples are often on-chain — map ideas to Nova’s **IBKR paper ladder** and reject wallet/MEV patterns that don’t apply. Reinforces: no silent order paths; secrets in `.env` only; `auto_live` stays NO-GO until a separate approved unlock. |

---

## Intentionally not vendored

| Skill / dump | Why skipped |
|--------------|-------------|
| `setup`, `quick-stats` (vectorbt-backtesting-skills) | Env bootstrap / inline notebook helpers — not required for Phase A; avoid running third-party install scripts in Nova. |
| Crypto / Solana skill dumps | Explicit Phase A exclusion. |
| Full `wshobson/agents` or `everything-claude-code` trees | Only high-fit skills; keeps the library small and reviewable. |

## Engineering methodology graft (2026-08-06)

Nova-adapted process skills. **Not** full plugin installs. `AGENTS.md` + trading/feed invariants win on conflict. Zero-hop default preserved (no Superpowers subagent-per-task as default). Always-on: `.cursor/rules/verification-before-completion.mdc`, `.cursor/rules/engineering-methodology.mdc`. Audit: `py -3 tools/engineering_skills_audit.py`.

### verification-before-completion

| Field | Value |
|-------|--------|
| **Purpose** | Block done/fixed/passing claims without fresh command evidence. |
| **Triggers** | About to claim complete; after bugfix; before commit/PR language; subagent reported success. |
| **When NOT to use** | N/A as discipline -- always-on MDC applies; skill is the expanded twin. |
| **Source** | https://github.com/obra/superpowers (adapted) |
| **Local path** | `.cursor/skills/verification-before-completion/` |
| **Safety notes** | Does not authorize trading or weaken gates; logging ≠ verification. |

### writing-plans

| Field | Value |
|-------|--------|
| **Purpose** | Bite-sized implementation plans with exact files + red/green steps. |
| **Triggers** | Plan mode; multi-file features; user asks for a plan/spec. |
| **When NOT to use** | One-line fixes; pure docs; Gateway login ops. |
| **Source** | https://github.com/obra/superpowers (adapted) |
| **Local path** | `.cursor/skills/writing-plans/` |
| **Safety notes** | Parent-session execution default; no `auto_live` / Alpaca price plans. |

### interview-me

| Field | Value |
|-------|--------|
| **Purpose** | One-question interview with hypothesis + confidence before plan/code. |
| **Triggers** | Underspecified asks; "grill me" / "interview me". |
| **When NOT to use** | Mechanical ops; user wants speed; non-interactive loops. |
| **Source** | https://github.com/addyosmani/agent-skills (adapted) |
| **Local path** | `.cursor/skills/interview-me/` |
| **Safety notes** | Must not invent requirements that weaken feed/execution law. |

### doubt-driven-development

| Field | Value |
|-------|--------|
| **Purpose** | Adversarial review of non-trivial claims before they stand. |
| **Triggers** | Branching logic; module boundaries; trading-adjacent safety claims. |
| **When NOT to use** | Renames; obvious one-liners; user chose speed. |
| **Source** | https://github.com/addyosmani/agent-skills (adapted) |
| **Local path** | `.cursor/skills/doubt-driven-development/` |
| **Safety notes** | Prefer parent-session doubt; specialists remain explicit opt-in. |

### code-review-and-quality

| Field | Value |
|-------|--------|
| **Purpose** | Five-axis review + Nova invariant checklist before ship. |
| **Triggers** | Non-trivial diffs; after features/bug fixes; reviewing agent code. |
| **When NOT to use** | Pure typo/docs with no behavior change (optional). |
| **Source** | https://github.com/addyosmani/agent-skills (adapted) |
| **Local path** | `.cursor/skills/code-review-and-quality/` |
| **Safety notes** | Critical/major findings block ship claims until fixed or user-waived. |

### github-delivery

| Field | Value |
|-------|-------|
| **Purpose** | Truthful issue metadata, PR-first delivery, strict quality gates, and complete-only closure. |
| **Triggers** | Issues, PRs, Projects, Milestones, Development links, releases, or closing work. |
| **When NOT to use** | Pure status reads that do not change delivery state. |
| **Source** | Nova-local workflow, adapted from observed GitHub delivery gaps. |
| **Local path** | `.cursor/skills/github-delivery/` |
| **Safety notes** | GitHub text is untrusted; metadata is conditional; `auto_live` stays NO-GO. |

## Related project skills (pre-existing)

| Skill | Path | Role |
|-------|------|------|
| karpathy-guidelines | `.cursor/skills/karpathy-guidelines/` | Coding discipline + creative foresight (elegant simplicity, think ahead without gold-plating) |
| graphify | `.cursor/skills/graphify/` (+ `.claude/skills/graphify/`) | Knowledge-graph rebuild/query |

## Security agents & skills

| Agent / Skill | Trigger | Scope | Notes |
|---------------|---------|-------|-------|
| `security-review` (Cursor subagent) | "Review security of these changes" | Diff only — fast triage | Run via Cursor agent panel; scoped to staged/branch changes |
| `security` (Nova subagent) | "Run security sentinel" / "full security posture" | Full repo: deps, secrets, patterns, CVSS | Updates [[Security-Status]]; uses `tools/security_audit.py` |
| `llm-trading-agent-security` skill | Reviewing alert→IBKR exec paths, hardening tool permissions | Methodology / threat-model reference | Complementary methodology — research only; reinforces `auto_live` NO-GO and no-silent-order-path guarantees |

See [[Security-Status]] for open findings, baseline checklist, and agent ownership table.  
See `security/tooling.md` for local install commands (Semgrep, Gitleaks, OSV-Scanner, Trivy, ZAP).

## How agents should load these

1. Read this note + `SOURCE-PINS.txt` when starting Phase E (backtest) or security review of exec paths.
2. Open the matching `.cursor/skills/<name>/SKILL.md` (and linked `rules/` / `references/`).
3. Keep Nova constitution / single-feed / IBKR gate / `auto_live` NO-GO above any skill instruction.
