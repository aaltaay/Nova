/**
 * Pure row helpers for the HOD Momo strip: which alerts a mode shows, the
 * one-line gate text, clock + "since" labels. No module state.
 */
import {
  HOD_MOMO_STRIP_GATE_KEYS,
  HOD_MOMO_STRIP_GATE_LABEL,
  HOD_MOMO_STRIP_NO_GATE_VALUES,
} from './hodMomoStripConstants';
import { partitionScannerAlerts } from './scannerPartition';
import type { HodDockMode } from './scannerDockModes';
import type { AlertObject } from './types';

export type StripGateValue = { key: string; label: string; value: string };

function alertDate(alert: Pick<AlertObject, 'timestamp' | 'created_ts'>): Date | null {
  if (alert.timestamp) {
    const parsed = new Date(alert.timestamp);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  if (typeof alert.created_ts === 'number' && alert.created_ts > 0) {
    const ms = alert.created_ts > 1e12 ? alert.created_ts : alert.created_ts * 1000;
    const d = new Date(ms);
    if (!Number.isNaN(d.getTime())) return d;
  }
  return null;
}

/** HH:MM:SS, 24h, in the viewer's clock -- the same clock the old table used. */
export function fmtStripClock(alert: Pick<AlertObject, 'timestamp' | 'created_ts'>): string {
  const d = alertDate(alert);
  if (!d) return '—';
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

/** HH:MM of the oldest alert in the list -- what "since" means on the header. */
export function fmtStripSince(alerts: readonly AlertObject[]): string | null {
  let oldest: Date | null = null;
  for (const a of alerts) {
    const d = alertDate(a);
    if (d && (!oldest || d.getTime() < oldest.getTime())) oldest = d;
  }
  if (!oldest) return null;
  return oldest.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function fmtPct(v: number): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function fmtShares(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(Math.round(v));
}

/** The gate values the alert carries, in a fixed order; a null field is a
 * stated dash, never a guess. */
export function alertGateValues(alert: AlertObject): StripGateValue[] {
  return HOD_MOMO_STRIP_GATE_KEYS.map((key) => {
    const raw = alert[key];
    const label = HOD_MOMO_STRIP_GATE_LABEL[key];
    if (raw == null || !Number.isFinite(raw)) return { key, label, value: '—' };
    switch (key) {
      case 'change_pct':
      case 'gap_pct':
      case 'momentum_pct':
        return { key, label, value: fmtPct(raw) };
      case 'rvol':
      case 'rvol_5min':
        return { key, label, value: `${raw.toFixed(1)}×` };
      case 'float_shares':
      case 'volume':
        return { key, label, value: fmtShares(raw) };
      default:
        return { key, label, value: String(raw) };
    }
  });
}

/** True when every gate value is absent -- the row says so instead of showing seven dashes. */
export function gateValuesAllAbsent(values: readonly StripGateValue[]): boolean {
  return values.every((v) => v.value === '—');
}

export const HOD_MOMO_STRIP_GATE_ABSENT_TEXT = HOD_MOMO_STRIP_NO_GATE_VALUES;

export function fmtStripPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(2);
}

/**
 * Alerts the strip shows for a mode, newest first (the stream is newest-first
 * already; this keeps that order and never re-sorts by symbol). The strategy
 * filter applies to the HOD side only -- Running Up is one strategy.
 */
export function stripAlertsForMode(
  alerts: readonly AlertObject[],
  mode: HodDockMode,
  visibleStrategies: ReadonlySet<number> | null,
): AlertObject[] {
  const { hodMomentum, runningUp } = partitionScannerAlerts([...alerts]);
  if (mode === 'running_up') return runningUp;
  if (!visibleStrategies) return hodMomentum;
  return hodMomentum.filter((a) => visibleStrategies.has(a.strategy_id));
}
