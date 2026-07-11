# News Impact Decision Layer

> Explicit, rules-first judgment of whether news actually affects a ticker / Level 2.
> Not a black box — every threshold lives in `backend/constants.py` (`NEWS_IMPACT_*`)
> and is echoed in each verdict's `factors` + `reasons[]`.

**Status:** Implemented (rules-v1). Lincoln AI reasoning slot is a placeholder (`ai_reasoning: null`).
**Last updated:** 2026-07-11

---

## What already existed

- Alpaca news fetch + flame age badges (`NEWS_FLAME_*`)
- News-first catalyst scan (`/api/news-catalysts`) with headline + gap
- Five Pillars / watchlist catalyst freshness score (binary `has_news` + age decay)
- L2 feature math (`backend/l2/features.py`) for imbalance / bid-heavy

## What this layer adds

`GET /api/news/impact/{symbol}` and `news_impact` on ticker detail / catalyst rows.

### Impact classes (plain English)

| Class | Meaning |
|-------|---------|
| `moved_price` | Bump appears **due to** news (fresh/aging headline + mild/strong price move) |
| `attention_only` | News got attention (elevated RVOL) **without** a meaningful price move |
| `no_effect` | News did **not** affect the ticker (flat price, or headline too old to attribute) |
| `insufficient_data` | Missing articles and/or market context |

### Visible factors

1. **Age** — fresh ≤ 2h, aging ≤ 6h, stale ≤ 24h, else expired
2. **Source tier** — official / major / secondary / unknown (keyword lists in constants)
3. **Official confirmation** — official source OR ≥ 2 major/official sources
4. **Price reaction** — strong ≥ 10% \|gap\|, mild ≥ 3%, else flat
5. **Attention** — RVOL ≥ 2×
6. **Level 2** — reacting if bid-heavy or \|imbalance\| ≥ 0.35; else quiet / insufficient_data
7. **`ai_reasoning`** — always `null` until Lincoln AI is wired

Tune by editing `NEWS_IMPACT_*` in `backend/constants.py` only.
