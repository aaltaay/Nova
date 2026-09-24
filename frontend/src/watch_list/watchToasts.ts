/**
 * Toasts for watched symbols: the HOD Momo feed -- HOD Momo strategies and
 * Running Up (strategy 12) alike (operator ask, 2026-09-23) -- and the setup
 * scanner, a setup climbing its ladder (setupClimbs.ts, operator ask
 * 2026-09-24). One toast per symbol: another event for a symbol already on
 * screen updates that toast (newest event in the title, its alert or setup
 * line added) and restarts its timer, so a burst of strategies firing together
 * is one toast, not five. While a toast is up its setup lines follow the board
 * (refreshWatchSetupLines) without restarting the timer.
 */
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID } from '../constants';
import type { AlertObject } from '../hod_momo';
import { setupTypeOf, type SetupRow } from '../setups';
import type { WatchSetupClimb } from './setupClimbs';
import type { WatchSetupStage } from './types';
import { WATCH_TOAST_MAX } from './watchListConstants';
import { isWatched } from './watchListStore';

/** One setup on a toast: the climb that raised it, and its row as the board lists it now. */
export interface WatchSetupLine {
  setupType: string;
  stage: WatchSetupStage;
  row: SetupRow;
  /** False once the board stops listing it (back to watching, or no longer a name the scanner follows). */
  listed: boolean;
}

/** What the title names: the toast's newest event. `at` is the setup frame's epoch seconds. */
export type WatchToastHead =
  | { kind: 'hod' }
  | { kind: 'setup'; setupType: string; stage: WatchSetupStage; setupKind: string | null; at: number };

export interface WatchToast {
  symbol: string;
  /** The newest HOD Momo feed alert; null while only setups raised the toast. */
  alert: AlertObject | null;
  /** Distinct strategy names, newest first. */
  strategies: readonly string[];
  /** HOD Momo feed alerts folded in. */
  count: number;
  /** True once a HOD Momo strategy (not Running Up) is folded in -- the toast says "hit HOD Momo". */
  hod: boolean;
  /** One line per setup that climbed while the toast was up, newest first. */
  setups: readonly WatchSetupLine[];
  head: WatchToastHead;
  /** When the newest event arrived here (ms); the dismiss timer restarts from it. */
  lastAt: number;
}

export function isRunningUpAlert(alert: Pick<AlertObject, 'strategy_id'>): boolean {
  return alert.strategy_id === HOD_MOMO_RUNNING_UP_STRATEGY_ID;
}

function place(toasts: readonly WatchToast[], next: WatchToast, max: number): WatchToast[] {
  return [next, ...toasts.filter(t => t.symbol !== next.symbol)].slice(0, Math.max(1, max));
}

/** Pure: `toasts` with `alert` folded in, newest toast first, at most `max`. */
export function withWatchAlert(
  toasts: readonly WatchToast[],
  alert: AlertObject,
  nowMs: number,
  max: number = WATCH_TOAST_MAX,
): WatchToast[] {
  const symbol = String(alert.ticker ?? '').trim().toUpperCase();
  if (!symbol) return [...toasts];
  const name = (alert.strategy_name ?? '').trim();
  const prior = toasts.find(t => t.symbol === symbol);
  const strategies = prior
    ? [name, ...prior.strategies.filter(s => s !== name)].filter(Boolean)
    : (name ? [name] : []);
  return place(toasts, {
    symbol,
    alert,
    strategies,
    count: (prior?.count ?? 0) + 1,
    hod: Boolean(prior?.hod) || !isRunningUpAlert(alert),
    setups: prior?.setups ?? [],
    head: { kind: 'hod' },
    lastAt: nowMs,
  }, max);
}

/** Pure: `toasts` with a setup's climb folded in: its line first, the title its. */
export function withWatchSetup(
  toasts: readonly WatchToast[],
  climb: WatchSetupClimb,
  nowMs: number,
  max: number = WATCH_TOAST_MAX,
): WatchToast[] {
  const symbol = climb.symbol.trim().toUpperCase();
  if (!symbol) return [...toasts];
  const prior = toasts.find(t => t.symbol === symbol);
  const line: WatchSetupLine = { setupType: climb.setupType, stage: climb.stage, row: climb.row, listed: true };
  return place(toasts, {
    symbol,
    alert: prior?.alert ?? null,
    strategies: prior?.strategies ?? [],
    count: prior?.count ?? 0,
    hod: prior?.hod ?? false,
    setups: [line, ...(prior?.setups ?? []).filter(l => l.setupType !== climb.setupType)],
    head: { kind: 'setup', setupType: climb.setupType, stage: climb.stage, setupKind: climb.row.kind, at: climb.at },
    lastAt: nowMs,
  }, max);
}

/**
 * Pure: every setup line on `toasts` as the board lists it now -- its newest row,
 * or unlisted when the board dropped it. Timers and counts are untouched. Returns
 * `toasts` itself when no toast carries a setup line.
 */
export function withSetupRows(toasts: readonly WatchToast[], rows: readonly SetupRow[]): readonly WatchToast[] {
  if (!toasts.some(t => t.setups.length > 0)) return toasts;
  const byKey = new Map<string, SetupRow>();
  for (const row of rows) {
    const key = `${String(row.symbol ?? '').toUpperCase()}|${setupTypeOf(row)}`;
    if (!byKey.has(key)) byKey.set(key, row);
  }
  return toasts.map(toast => {
    if (toast.setups.length === 0) return toast;
    const setups = toast.setups.map(line => {
      const row = byKey.get(`${toast.symbol}|${line.setupType}`);
      if (row) return { ...line, row, listed: true };
      return line.listed ? { ...line, listed: false } : line;
    });
    return { ...toast, setups };
  });
}

let toasts: readonly WatchToast[] = [];
const listeners = new Set<() => void>();

function publish(next: readonly WatchToast[]): void {
  toasts = next;
  listeners.forEach(fn => fn());
}

/** A live HOD Momo feed alert (Running Up included): toast it when its symbol is watched. Returns whether it toasted. */
export function noteWatchedHodAlert(alert: AlertObject, nowMs: number = Date.now()): boolean {
  if (!isWatched(String(alert.ticker ?? ''))) return false;
  publish(withWatchAlert(toasts, alert, nowMs));
  return true;
}

/** A setup's climb on the live board: toast it when its symbol is watched. Returns whether it toasted. */
export function noteWatchedSetupClimb(climb: WatchSetupClimb, nowMs: number = Date.now()): boolean {
  if (!isWatched(climb.symbol)) return false;
  publish(withWatchSetup(toasts, climb, nowMs));
  return true;
}

/** A new live board frame: the setup lines on screen follow it. */
export function refreshWatchSetupLines(rows: readonly SetupRow[]): void {
  const next = withSetupRows(toasts, rows);
  if (next !== toasts) publish(next);
}

export function dismissWatchToast(symbol: string): void {
  const next = toasts.filter(t => t.symbol !== symbol);
  if (next.length !== toasts.length) publish(next);
}

export function getWatchToasts(): readonly WatchToast[] {
  return toasts;
}

export function subscribeWatchToasts(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Test-only. */
export function resetWatchToastsForTests(): void {
  publish([]);
}
