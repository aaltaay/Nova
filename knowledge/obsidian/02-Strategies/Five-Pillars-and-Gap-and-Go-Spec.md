# Five Pillars + Gap and Go — Technical Spec (implemented)

> This is the technical companion to `03-Nova-Decisions/Automation-Strategy-Backbone.md`.
> The backbone explains *why*; this file explains *what was built and how it works*.
> Status: **Phase 1 — signal only. No order-placing code exists in either module.**

---

## 1. Five Pillars scoring (`backend/strategy/five_pillars.py`)

Every candidate stock is scored against 5 independent pillars. A stock only earns the
✅ checkmark when **all 5** pass — partial matches show as `3/5`, `4/5`, etc. Thresholds
live in `backend/constants.py` (never hardcoded in the strategy module):

| Pillar | Constant | Default | Pass condition |
|---|---|---|---|
| 1. Price | `FIVE_PILLARS_MIN_PRICE` / `_MAX_PRICE` | $2.00–$20.00 | price is inside the band |
| 2. % Change | `FIVE_PILLARS_MIN_CHANGE_PCT` | ≥10% | up at least this % vs prior close |
| 3. Relative Volume | `FIVE_PILLARS_MIN_REL_VOLUME` | ≥5x | today's volume ÷ average volume |
| 4. Catalyst | — | news OR technical breakout | `has_news` flag, or explicit override |
| 5. Float | `FIVE_PILLARS_MAX_FLOAT_SHARES` | ≤20,000,000 shares | smaller float = bigger % moves |

**Design choices:**
- `evaluate_five_pillars(candidate: dict)` accepts the exact dict shape Nova's scanner
  already produces (`symbol`, `price`/`current_price`, `change_pct`/`gap_percent`,
  `rel_volume`, `has_news`, `float`/`float_shares`) — no new data plumbing needed.
- Missing data **fails closed** (e.g. unknown float never counts as a pass).
- `evaluate_many(candidates)` scores an entire watchlist (e.g. the live gapper cache) at once.
- `FivePillarsResult.to_dict()` returns a JSON-serializable payload with a `checkmark` field
  ready for direct UI rendering.

## 2. Gap and Go setup (`backend/strategy/gap_and_go.py`)

Adds the mechanical, codeable parts of the Gap and Go setup on top of the Five Pillars:

1. **Five Pillars gate** — must be all-pass first (import from `five_pillars.py`).
2. **Entry time window** — `GAP_AND_GO_WINDOW_START_ET` / `_END_ET` (default 9:30–10:00 AM ET).
3. **Pre-market high break** — the highest high among bars timestamped before 9:30 AM ET;
   `triggered = current_price > premarket_high`.
4. **Entry/stop/target math** — if all three gates pass:
   - `entry_price` = current price
   - `stop_price` = entry − `GAP_AND_GO_MAX_STOP_DOLLARS` (default $0.20/share)
   - `target_price` = entry + risk × `GAP_AND_GO_MIN_PROFIT_LOSS_RATIO` (default 2:1)

**Explicitly out of scope (see backbone §3):** Level 2 / time-and-sales exit judgment,
discretionary "feel" for the tape, and catalyst-quality judgment. These are not encoded
here on purpose — they need a human or a later, separately-designed module.

**Hard safety property:** `GapAndGoSignal.would_execute` is hard-coded `False` in every
code path. `eligible` tells you whether the setup is valid; it never causes an order.

## 3. Read-only API (`backend/routes/strategy.py`)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/strategy/five-pillars` | Five Pillars score for every symbol in the live gapper cache |
| GET | `/api/strategy/five-pillars/{symbol}` | Score for one symbol (404 if not in the gapper list) |
| GET | `/api/strategy/gap-and-go/{symbol}` | Full Gap and Go signal, using today's 5-min bars |

Every response includes a `note` field: *"Signal only. This endpoint never places, modifies,
or cancels orders."* There is no `POST`/`PUT`/`DELETE` verb anywhere in this router — by
design, not by convention, so it can't accidentally grow an execution path later without a
deliberate new file.

## 4. Tests (mock data, no network, no broker calls)

- `backend/tests/test_five_pillars.py` — 12 tests: every pillar fails independently, the
  "all pass → checkmark" case, scanner-field-name compatibility, and a full mock watchlist scan.
- `backend/tests/test_gap_and_go.py` — 10 tests: time-window edges, premarket-high-break
  logic, the Five-Pillars gate blocking an otherwise-triggered signal, entry/stop/target math,
  and an explicit assertion that `would_execute` is always `False`.
- Run: `py -3 -m pytest backend/tests/test_five_pillars.py backend/tests/test_gap_and_go.py -v`
  → 22/22 passed as of 2026-07-10.

## 5. UI transparency principle (applies to every future control)

Any button, toggle, or panel that touches automation must say, in plain language next to the
control, **exactly** what happens when it's used and what it does *not* do — e.g. "Signal
only — shows the Gap and Go checklist, places no orders" vs. "Paper trade — sends a bracket
order to your IBKR paper account, never live." No control should surprise the user with
behavior they weren't told about up front. There is currently **no "Automate" button in the
Nova UI** — this spec and the backbone doc are the foundation for building one later, once
the phased plan (backbone §5) reaches that point.
