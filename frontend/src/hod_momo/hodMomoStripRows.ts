/**
 * Pure row helpers for the HOD Momo strip: which alerts a mode shows, the
 * one-line gate text, clock + "since" labels. No module state.
 */
import {
  HOD_MOMO_STRIP_GATE_KEYS,
  HOD_MOMO_STRIP_GATE_LABEL,
  HOD_MOMO_STRIP_NO_GATE_VALUES,
  HOD_MOMO_STRIP_PRINT_LAG_NOTE_SEC,
} from './hodMomoStripConstants';
import { STOCK_VIEW_CLOCK_TIMEZONE } from '../constantGroups/chart_api';
import { alertIdentity, uniqueAlerts } from './hodMomoWire';
import { partitionScannerAlerts } from './scannerPartition';
import type { HodDockMode } from './scannerDockModes';
import type { AlertObject } from './types';

export type StripGateValue = { key: string; label: string; value: string };

/** When Nova raised the alert (`created_ts`, seconds or ms). */
function raisedDate(alert: Pick<AlertObject, 'created_ts'>): Date | null {
  if (typeof alert.created_ts === 'number' && Number.isFinite(alert.created_ts) && alert.created_ts > 0) {
    const ms = alert.created_ts > 1e12 ? alert.created_ts : alert.created_ts * 1000;
    const d = new Date(ms);
    if (!Number.isNaN(d.getTime())) return d;
  }
  return null;
}

/** The print that triggered the alert (`timestamp`, ISO). */
function printDate(alert: Pick<AlertObject, 'timestamp'>): Date | null {
  if (!alert.timestamp) return null;
  const parsed = new Date(alert.timestamp);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * The strip's clock and order are when Nova raised the alert: an alert raised
 * now on a print hours old used to show the old print's time and sit out of
 * order (QA V16). The print time rides in the row title (stripPrintNote).
 */
function alertDate(alert: Pick<AlertObject, 'timestamp' | 'created_ts'>): Date | null {
  return raisedDate(alert) ?? printDate(alert);
}

/** Epoch ms the strip orders and groups by (raise time, else print time); null when neither parses. */
export function stripAlertMs(alert: Pick<AlertObject, 'timestamp' | 'created_ts'>): number | null {
  return alertDate(alert)?.getTime() ?? null;
}

/** ET, whatever the browser's zone: the header clock, orders and charts are ET (QA W24). */
function clockOf(d: Date): string {
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
  });
}

/** HH:MM:SS, 24h, Eastern -- the desk's one clock. */
export function fmtStripClock(alert: Pick<AlertObject, 'timestamp' | 'created_ts'>): string {
  const d = alertDate(alert);
  return d ? clockOf(d) : '—';
}

/** "print 19:53:32, 3h 47m before the alert" when the trigger print is older than the alert. */
export function stripPrintNote(alert: Pick<AlertObject, 'timestamp' | 'created_ts'>): string | null {
  const raised = raisedDate(alert);
  const print = printDate(alert);
  if (!raised || !print) return null;
  const lagSec = Math.round((raised.getTime() - print.getTime()) / 1000);
  if (lagSec < HOD_MOMO_STRIP_PRINT_LAG_NOTE_SEC) return null;
  const m = Math.floor(lagSec / 60);
  const lag = m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : m > 0 ? `${m}m` : `${lagSec}s`;
  return `print ${clockOf(print)}, ${lag} before the alert`;
}

/** Newest raised first; ties keep the stream order (a stable sort). */
export function newestFirst(alerts: readonly AlertObject[]): AlertObject[] {
  const at = (a: AlertObject) => alertDate(a)?.getTime() ?? 0;
  return alerts
    .map((alert, index) => ({ alert, index, t: at(alert) }))
    .sort((a, b) => b.t - a.t || a.index - b.index)
    .map((x) => x.alert);
}

/** HH:MM of the oldest alert in the list -- what "since" means on the header. */
export function fmtStripSince(alerts: readonly AlertObject[]): string | null {
  let oldest: Date | null = null;
  for (const a of alerts) {
    const d = alertDate(a);
    if (d && (!oldest || d.getTime() < oldest.getTime())) oldest = d;
  }
  if (!oldest) return null;
  return oldest.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
  });
}

function fmtPct(v: number): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function fmtShares(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(Math.round(v));
}

function fmtGateValue(key: (typeof HOD_MOMO_STRIP_GATE_KEYS)[number], v: number): string {
  switch (key) {
    case 'change_pct':
    case 'gap_pct':
    case 'momentum_pct':
      return fmtPct(v);
    case 'rvol':
    case 'rvol_5min':
      return `${v.toFixed(1)}×`;
    case 'float_shares':
    case 'volume':
      return fmtShares(v);
    default:
      return String(v);
  }
}

/**
 * The gate values a set of alerts carries, in a fixed order. One alert reads
 * its own values; several (one ticker's strategies fired together) read the
 * shared value, or the low-high range where they differ -- momentum is
 * measured over each strategy's own window. A field no member carries is a
 * stated dash, never a guess.
 */
export function gateValuesOf(alerts: readonly AlertObject[]): StripGateValue[] {
  return HOD_MOMO_STRIP_GATE_KEYS.map((key) => {
    const label = HOD_MOMO_STRIP_GATE_LABEL[key];
    const known = alerts
      .map((a) => a[key])
      .filter((v): v is number => v != null && Number.isFinite(v));
    if (known.length === 0) return { key, label, value: '—' };
    const lo = fmtGateValue(key, Math.min(...known));
    const hi = fmtGateValue(key, Math.max(...known));
    return { key, label, value: lo === hi ? lo : `${lo}–${hi}` };
  });
}

/** The gate values the alert carries, in a fixed order; a null field is a
 * stated dash, never a guess. */
export function alertGateValues(alert: AlertObject): StripGateValue[] {
  return gateValuesOf([alert]);
}

/** The backend's burst badge: "22 in 5s" when it consolidated repeat fires, else null. */
export function stripBurstText(alert: Pick<AlertObject, 'consolidation_count' | 'consolidation_span_sec'>): string | null {
  if (!(alert.consolidation_count > 1)) return null;
  return `${alert.consolidation_count} in ${Math.max(1, alert.consolidation_span_sec ?? 1)}s`;
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
 * Alerts the strip shows for a mode: exact duplicates dropped, newest raised
 * first (the stream is not reliably ordered -- QA V16), never re-sorted by
 * symbol. The strategy filter applies to the HOD side only -- Running Up is
 * one strategy.
 */
export function stripAlertsForMode(
  alerts: readonly AlertObject[],
  mode: HodDockMode,
  visibleStrategies: ReadonlySet<number> | null,
): AlertObject[] {
  const { hodMomentum, runningUp } = partitionScannerAlerts(newestFirst(uniqueAlerts(alerts)));
  if (mode === 'running_up') return runningUp;
  if (!visibleStrategies) return hodMomentum;
  return hodMomentum.filter((a) => visibleStrategies.has(a.strategy_id));
}

/** React key for a strip row: id plus raise time (legacy ids could repeat). */
export const stripAlertKey = alertIdentity;
