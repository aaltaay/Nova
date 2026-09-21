# ADR 019 -- The Sim venue is a practice desk on replayed real sessions

**Status:** Accepted · **Date:** 2026-09-20
**Builds on:** [[017-single-replay-surface]] · [[018-desk-venue-vs-spend-arming]]
**Decision issues:** #315 · #310 · #340 · #309

## Context

`SIM1` was a synthetic instrument: a looping sine-wave tape with a fabricated
book, injected into the quote, Time & Sales, Level 2, chart and scanner
whenever the desk sat in the Sim venue. It began as a way to exercise the desk
on a weekend with no Gateway, and it spread:

- practice orders were refused for every symbol except `SIM1`
  (`"SIM v1 only serves SIM1"`), so a real replayed day was watch-only -- the
  single largest gap between what replay is and what it is for (#310);
- the recorder carried `SIM1` exemptions, including a manifest that claimed
  `source: "sim"` and a skipped empty-segment check, which is the shape of the
  bug in #315 -- a recording that reports success while holding nothing;
- with a capture selection cleared, the desk fell back to synthetic ticks, so
  "no data" and "fake data" looked identical on screen.

The operator's decision (2026-09-20, recorded on #315 and #310) is that `SIM1`
was a temporary test ticker, never a product feature, and that keeping it
around creates confusion. The intended workflow is: select a real ticker,
receive actual market data, record it, replay that recording, and practise
against it without placing live orders.

## Decision

1. **`SIM1` is deleted.** No synthetic instrument, tape, book, bar seed or
   scanner row exists anywhere. With no replay loaded, the Sim venue serves no
   quote, no book, no prints and no bars -- an empty desk, never a fabricated
   one. `replay_source` reports `none` rather than `synthetic`.

2. **The Sim venue trades the loaded replay.** A practice order is admitted
   only for the symbol of a loaded historical download (with trades) or a
   recorded capture, and only once that replay has printed at the playhead.
   Refusals are explicit (`SIM_NO_REPLAY`, `SIM_SYMBOL_MISMATCH`,
   `SIM_NO_TRADES`, `SIM_NO_PRICE`).

3. **Fills are estimates, and say so.** `architecture/practice-fills.md` is the
   contract: which rule produced a fill, what it assumes, and which biases it
   carries. Every filled row carries `fill_estimated` and a `fill_basis`, so a
   practice fill is never presented as a recorded print. `MKT`, `LMT` and `STP`
   are supported; brackets stay off the practice desk.

4. **Getting flat always works.** A protective source (`flatten`, `kill`,
   `cancel_working`) may close an existing practice position with a market
   order even when its replay is no longer loaded; the fill takes the last
   known mark. This preserves ADR 018's rule that a desk can always get flat,
   and it cannot open exposure -- the ledger admits it only when it reduces a
   held position.

5. **The recorder has no exemptions.** Every recording is IBKR-sourced and
   must pass producer admission (a connected, non-rejected AllLast
   subscription for the selected symbol). A segment that ends with no prints
   finalizes as `failed`. A print that arrives without an exchange timestamp is
   recorded with `ts_source: "receive"`, so a substituted time never reads as
   the exchange's own.

## Consequences

- Sim stops being a 24/7 toy and becomes the review-and-practise surface for
  real days: load a day, scrub it, and trade it.
- The weekend "always something moving on screen" affordance is gone. With
  nothing loaded the desk is deliberately empty and says what to load.
- Practice results are only as good as the fill model, which is why its biases
  are written down rather than implied.
- `backend/sensors/` reads the same depth and tape pipes in every venue and
  labels replayed data `replay`; it no longer has a Sim-only branch.
- This supersedes ADR 017's note that "SIM1 manifests identify sim provenance"
  and its consequence that "practice fills on historical symbols remain
  disabled pending #310". ADR 017's replay-surface ownership is unchanged.

## Rejected alternatives

- **Keep `SIM1` and restrict Record to it.** The cheap fix for #315, and the
  one first proposed. Rejected by the operator: it preserves a fake instrument
  whose whole value was standing in for the real one.
- **Keep replay read-only (close #310).** Removes the fill-model risk and
  leaves the practice desk unable to practise. Rejected.
- **Fill practice orders from candles when trades were not downloaded.** A
  candle is not a print; inferring fills from OHLC would invent a trade
  sequence that never existed. Refused with `SIM_NO_TRADES` instead.
- **Model queue position and partial fills.** Materially more work, and the
  inputs (book depth over time for the replayed day) do not exist on the
  historical source. Documented as a known bias instead.

## Related

- `architecture/practice-fills.md` · `docs/sim-mode.md`
- `backend/sim/practice.py` · `backend/sim/fill_model.py` · `backend/sim/broker.py`
- `.cursor/rules/capture-replay-truth.mdc` · `.cursor/rules/single-market-data-feed.mdc`
