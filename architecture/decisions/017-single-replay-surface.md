# ADR 017 -- One historical replay surface and one IBKR trade-print source

**Status:** Accepted · **Date:** 2026-09-20
**Builds on:** [[010-ib-loop-isolation]] · [[012-local-first-chart-bars]]
**Decision issue:** #340 · **Unblocks:** #315, #308

## Context

Nova has three overlapping market-recording paths:

1. `backend/sim/history_*` downloads IBKR historical trades/bars into a durable
   SQLite job store and drives the operator's Historical replay controls.
2. `backend/capture/` records a live tab to JSONL and
   `backend/sim/capture_player.py` plays those files directly.
3. `backend/l2/` stores short-lived depth sessions and tape rows for recall and
   feature work.

Only the first path has the durable job, coverage, resume, ordering and
no-lookahead contracts required by the Historical replay product. The other
two grew before the IBKR-only feed rule. Their documentation still described
Alpaca WebSocket trades as a valid time-and-sales source even though that
producer is disabled in IBKR mode. That allowed an empty recorder to look
healthy and left #315 blocked on an ownership choice.

## Decision

1. **`backend/sim/history_*` is the sole Historical replay engine and public
   replay surface.** It owns acquisition jobs, coverage, durable ordered event
   storage, playback snapshots, seek/no-lookahead behavior and the
   `/api/sim/history` contract. New replay capabilities extend this path rather
   than creating another player or store.

2. **IBKR AllLast is the sole production trade-print source.** The existing
   `backend/ibkr/tape_stream.py` subscription owns acquisition. Its normalized
   print must fan out off the IB callback/loop to every admitted consumer. No
   Alpaca market-data WebSocket may feed recording, replay, bars or the live
   tape when discovery is IBKR. Alpaca remains news and listing metadata only.

3. **`backend/capture/` becomes a feeder, not a replay engine.** It may keep
   recording an explicitly selected live tab, including quotes and depth that
   the historical API cannot acquire. Its normalized IBKR prints must be
   ingested through the canonical replay model before the operator can select
   them. Direct JSONL playback in `sim/capture_player.py` and the separate
   capture selection state in `sim/replay.py` are compatibility paths to retire
   after an importer preserves existing recordings. New behavior must not
   deepen either path.

4. **`backend/l2/` remains the hot depth/feature recorder.** Its
   `l2_snapshots`, session metadata and recall/labeling APIs stay useful. The
   orphaned `tape_trades` writer is not a replay authority; #315/#308 must
   either feed it from the same normalized IBKR fan-out with loud health, or
   migrate its consumers to the canonical store and retire the table. It may
   not open a second trade subscription.

5. **Nova OS `backend/archive/replay.py` is a decision-audit projection, not a
   fourth market replay surface.** It may consume archived canonical facts to
   re-run strategy decisions, but it does not own acquisition, playback UI or
   market-data truth.

## Migration contract for #315 / #308

- Normalize one IBKR AllLast event at the `tape_stream` boundary and dispatch
  immutable copies through a bounded off-loop fan-out.
- Admit a real-symbol recording only when that IBKR producer is subscribed and
  the selected symbol matches. Otherwise refuse or report unhealthy; never
  create a healthy empty manifest.
- Give each sink independent backpressure and health. A failed optional L2 or
  capture sink must not block the live tape, scanner, or IB loop.
- Preserve source, exchange, conditions, event timestamp and receive timestamp.
  Do not synthesize `$0.00` prints or infer missing quotes/depth.
- Add an import seam from legacy capture JSONL into the canonical history
  schema before deleting direct playback. Existing recordings remain readable
  during the compatibility window.

## Consequences

- #315 can proceed without choosing among competing engines: fix one IBKR
  producer/fan-out, then make empty or dead sinks loud.
- Historical downloads and live recordings can have different acquisition
  capabilities while sharing one replay contract.
- Quotes and depth remain absent from an IBKR historical replay until separately
  approved (#309/#311); this ADR does not invent them.
- Practice fills on historical symbols remain disabled pending #310. No broker
  execution path or trading gate changes; `auto_live` remains NO-GO.
- Retiring direct capture playback requires an importer and compatibility tests,
  so this ADR does not delete user recordings or silently reinterpret them.

## Rejected alternatives

- **Make `backend/capture/` the engine.** JSONL sessions lack durable jobs,
  atomic page cursors, explicit coverage and the established historical API.
- **Make `backend/l2/` the engine.** Its hot retention and feature-recall model
  are intentionally narrower than deterministic full-window playback.
- **Keep all three as peer replay implementations.** That preserves divergent
  schemas, duplicate health semantics and the ambiguity that caused #315.
- **Restore Alpaca trades for the dead recorder.** That violates the
  IBKR-only market-data invariant and would make replay disagree with the desk.

## Related

- `architecture/historical-replay.md`
- `backend/ibkr/tape_stream.py`
- `backend/sim/history_store.py`
- `backend/sim/history_playback.py`
- `backend/capture/`
- `backend/l2/`
- `.cursor/rules/single-market-data-feed.mdc`

## Implementation: live print feeder

The AllLast callback normalizes one immutable print and only enqueues recording work. Capture uses its bounded, generation-fenced writer; L2 uses an independent bounded worker. Admission requires the selected symbol's connected, non-rejected AllLast subscription. Status reports waiting/stale/disconnected/error explicitly; no-print sessions are not healthy evidence. SIM1 manifests identify sim provenance. Quotes and depth remain absent from this print-only feeder; no inferred rows are created. Legacy capture playback remains until the canonical importer is implemented.

