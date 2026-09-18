/**
 * Pure gate: ping only when a new HOD Momo *row* arrives.
 *
 * A table row is one ticker (`collapseAlertsBySymbol`). Re-fires of the same
 * name update that row in place and must not ping. Running Up shares the WS
 * but is a sibling list -- Ahmed's ask is the HOD Momo list only.
 *
 * StrategyConfig.audio is not this gate. That checkbox is per-strategy,
 * persisted on the backend, and has no playback consumer. The banner mute
 * is a desk-level localStorage switch (see hodMomoAlertSound.ts).
 */
import { isRunningUpStrategy } from './scannerPartition';

export type HodMomoSoundArrival = {
  id?: string;
  ticker?: string;
  timestamp?: string;
  strategy_id: number;
};

export type HodMomoSoundGate = {
  seenArrivals: Set<string>;
  seenRows: Set<string>;
};

export function createHodMomoSoundGate(): HodMomoSoundGate {
  return { seenArrivals: new Set(), seenRows: new Set() };
}

export function hodMomoArrivalKey(alert: HodMomoSoundArrival): string {
  const id = (alert.id || '').trim();
  if (id) return `id:${id}`;
  const ticker = (alert.ticker || '').trim().toUpperCase();
  const ts = (alert.timestamp || '').trim();
  return `sym:${ticker}|${ts}`;
}

export function hodMomoRowKey(alert: HodMomoSoundArrival): string {
  return (alert.ticker || '').trim().toUpperCase();
}

/** Replace gate from a WS `initial` payload (connect, reconnect, clear today). */
export function seedHodMomoSoundGate(
  alerts: readonly HodMomoSoundArrival[],
): HodMomoSoundGate {
  const next = createHodMomoSoundGate();
  for (const alert of alerts) {
    next.seenArrivals.add(hodMomoArrivalKey(alert));
    const row = hodMomoRowKey(alert);
    if (row && !isRunningUpStrategy(alert.strategy_id)) {
      next.seenRows.add(row);
    }
  }
  return next;
}

export function noteHodMomoSoundArrivals(
  gate: HodMomoSoundGate,
  arrivals: readonly HodMomoSoundArrival[],
): { gate: HodMomoSoundGate; newHodRows: number; shouldPing: boolean } {
  const seenArrivals = new Set(gate.seenArrivals);
  const seenRows = new Set(gate.seenRows);
  let newHodRows = 0;
  for (const alert of arrivals) {
    const arrival = hodMomoArrivalKey(alert);
    if (seenArrivals.has(arrival)) continue;
    seenArrivals.add(arrival);
    if (isRunningUpStrategy(alert.strategy_id)) continue;
    const row = hodMomoRowKey(alert);
    if (!row || seenRows.has(row)) continue;
    seenRows.add(row);
    newHodRows += 1;
  }
  return {
    gate: { seenArrivals, seenRows },
    newHodRows,
    shouldPing: newHodRows > 0,
  };
}

/** Testable compose: new HOD row + desk sound on. Coalesce lives in play(). */
export function evaluateHodMomoAlertPing(
  gate: HodMomoSoundGate,
  arrivals: readonly HodMomoSoundArrival[],
  soundOn: boolean,
): { gate: HodMomoSoundGate; play: boolean } {
  const noted = noteHodMomoSoundArrivals(gate, arrivals);
  return { gate: noted.gate, play: noted.shouldPing && soundOn };
}
