/**
 * Toasts for the hot list (ADR 044 amendment, operator ask 2026-10-12: "i get alot of stupid toast notifications
 * ... the way we have it codded is no good"). Three events can raise one: a HOD Momo feed alert, a setup climbing
 * its ladder on the setup scanner (setupClimbs.ts) and an auto star joining the list. Each passes the gate
 * (toastGate.ts): a star toasts on a HOD Momo strategy (never Running Up) and on its setups from armed up, an auto
 * star only when it joins, nothing outside the trading window (toastWindow.ts), and a stock's HOD Momo alerts stay
 * quiet a while after its toast. What the gate holds back is counted, and every raised toast is kept for scoring
 * (toastScores.ts).
 *
 * One toast per symbol: another raised event for a symbol on screen updates that toast (newest event in the title,
 * its alert or setup line added) and restarts its timer. A HOD Momo alert in the quiet period folds into the toast
 * on screen without restarting it. While a toast is up its setup lines follow the board (refreshWatchSetupLines)
 * without restarting the timer.
 */
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID } from '../constants';
import type { AlertObject } from '../hod_momo';
import type { HotListView } from '../hot_list';
import { setupTypeOf, type SetupRow } from '../setups';
import type { WatchSetupClimb } from './setupClimbs';
import { gateToast, type GateMemory, type ToastCandidate } from './toastGate';
import { recordHeld, recordToast, type ToastScoreKind } from './toastScores';
import { toastWindowOpen, tradingDayOf } from './toastWindow';
import type { WatchSetupStage } from './types';
import { WATCH_TOAST_JOIN_FRESH_MS, WATCH_TOAST_MAX } from './watchListConstants';
import { watchHow } from './watchListStore';

/** One setup on a toast: the climb that raised it, and its row as the board lists it now. */
export interface WatchSetupLine {
  setupType: string;
  stage: WatchSetupStage;
  row: SetupRow;
  /** False once the board stops listing it (back to watching, or no longer a name the scanner follows). */
  listed: boolean;
}

/** An auto star joining the list: where it stood on the Gainers board. `at` is epoch seconds. */
export interface WatchJoin {
  rank: number | null;
  /** The auto feed's top N at the time; null when the list did not say. */
  n: number | null;
  /** A fraction (0.6 = +60%), as on the hot list. */
  changePct: number | null;
  at: number;
}

/** What the title names: the toast's newest raised event. `at` is the setup frame's epoch seconds. */
export type WatchToastHead =
  | { kind: 'hod' }
  | { kind: 'join' }
  | { kind: 'setup'; setupType: string; stage: WatchSetupStage; setupKind: string | null; at: number };

export interface WatchToast {
  symbol: string;
  /** The newest HOD Momo feed alert; null while none was folded in. */
  alert: AlertObject | null;
  /** Distinct strategy names, newest first. */
  strategies: readonly string[];
  /** HOD Momo feed alerts folded in. */
  count: number;
  /** One line per setup that climbed while the toast was up, newest first. */
  setups: readonly WatchSetupLine[];
  /** Set when the toast announced an auto star joining the list. */
  join: WatchJoin | null;
  head: WatchToastHead;
  /** When the newest raised event arrived here (ms); the dismiss timer restarts from it. */
  lastAt: number;
}

export function isRunningUpAlert(alert: Pick<AlertObject, 'strategy_id'>): boolean {
  return alert.strategy_id === HOD_MOMO_RUNNING_UP_STRATEGY_ID;
}

function place(toasts: readonly WatchToast[], next: WatchToast, max: number): WatchToast[] {
  return [next, ...toasts.filter(t => t.symbol !== next.symbol)].slice(0, Math.max(1, max));
}

function blank(symbol: string): Omit<WatchToast, 'head' | 'lastAt'> {
  return { symbol, alert: null, strategies: [], count: 0, setups: [], join: null };
}

/**
 * Pure: `toasts` with `alert` folded in, newest toast first, at most `max`. `raise` false (the quiet period) only
 * updates the toast on screen -- its strategies, count and facts -- keeping its title, place and timer.
 */
export function withWatchAlert(
  toasts: readonly WatchToast[],
  alert: AlertObject,
  nowMs: number,
  max: number = WATCH_TOAST_MAX,
  raise = true,
): WatchToast[] {
  const symbol = String(alert.ticker ?? '').trim().toUpperCase();
  if (!symbol) return [...toasts];
  const name = (alert.strategy_name ?? '').trim();
  const prior = toasts.find(t => t.symbol === symbol);
  if (!raise && !prior) return [...toasts];
  const strategies = prior
    ? [name, ...prior.strategies.filter(s => s !== name)].filter(Boolean)
    : (name ? [name] : []);
  const next: WatchToast = {
    ...(prior ?? blank(symbol)),
    alert,
    strategies,
    count: (prior?.count ?? 0) + 1,
    head: raise || !prior ? { kind: 'hod' } : prior.head,
    lastAt: raise || !prior ? nowMs : prior.lastAt,
  };
  if (!raise) return toasts.map(t => (t.symbol === symbol ? next : t));
  return place(toasts, next, max);
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
    ...(prior ?? blank(symbol)),
    setups: [line, ...(prior?.setups ?? []).filter(l => l.setupType !== climb.setupType)],
    head: { kind: 'setup', setupType: climb.setupType, stage: climb.stage, setupKind: climb.row.kind, at: climb.at },
    lastAt: nowMs,
  }, max);
}

/** Pure: `toasts` with an auto star's join: the title its. */
export function withWatchJoin(
  toasts: readonly WatchToast[],
  symbol: string,
  join: WatchJoin,
  nowMs: number,
  max: number = WATCH_TOAST_MAX,
): WatchToast[] {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return [...toasts];
  const prior = toasts.find(t => t.symbol === sym);
  return place(toasts, { ...(prior ?? blank(sym)), join, head: { kind: 'join' }, lastAt: nowMs }, max);
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

/** Pure: the auto stars on `view` that joined within WATCH_TOAST_JOIN_FRESH_MS of `nowMs` -- a join is news only then. */
export function freshJoins(view: HotListView | null, nowMs: number): Array<{ symbol: string; join: WatchJoin }> {
  if (!view) return [];
  return view.entries.flatMap(e => {
    const atMs = e.at * 1000;
    if (e.how !== 'auto' || !(atMs >= nowMs - WATCH_TOAST_JOIN_FRESH_MS)) return [];
    return [{ symbol: e.symbol, join: { rank: e.rank, n: view.auto.n || null, changePct: e.change_pct, at: e.at } }];
  });
}

let toasts: readonly WatchToast[] = [];
let gate: GateMemory | null = null;
const listeners = new Set<() => void>();

function publish(next: readonly WatchToast[]): void {
  toasts = next;
  listeners.forEach(fn => fn());
}

/** The gate's word on `event` now: raise, fold, or nothing (held back -- counted -- or not listed). */
function pass(event: ToastCandidate, nowMs: number): 'raise' | 'fold' | null {
  const symbol = event.symbol.trim().toUpperCase();
  const { verdict, memory } = gateToast(gate, event, {
    nowMs,
    day: tradingDayOf(nowMs),
    inWindow: toastWindowOpen(nowMs),
    how: watchHow(symbol),
    onScreen: toasts.some(t => t.symbol === symbol),
  });
  gate = memory;
  if (verdict.verdict === 'hold') recordHeld(verdict.reason, nowMs);
  return verdict.verdict === 'raise' || verdict.verdict === 'fold' ? verdict.verdict : null;
}

/** A live HOD Momo feed alert for a listed symbol. Returns whether a toast showed it. */
export function noteWatchedHodAlert(alert: AlertObject, nowMs: number = Date.now()): boolean {
  const symbol = String(alert.ticker ?? '').trim().toUpperCase();
  if (!symbol) return false;
  const verdict = pass({ kind: 'hod', symbol, runningUp: isRunningUpAlert(alert) }, nowMs);
  if (!verdict) return false;
  publish(withWatchAlert(toasts, alert, nowMs, WATCH_TOAST_MAX, verdict === 'raise'));
  if (verdict === 'raise') recordToast(symbol, 'hod', alert.price ?? null, nowMs);
  return true;
}

/** A setup's climb on the live board for a listed symbol. Returns whether it toasted. */
export function noteWatchedSetupClimb(climb: WatchSetupClimb, nowMs: number = Date.now()): boolean {
  const symbol = climb.symbol.trim().toUpperCase();
  if (pass({ kind: 'setup', symbol, stage: climb.stage }, nowMs) !== 'raise') return false;
  publish(withWatchSetup(toasts, climb, nowMs));
  recordToast(symbol, climb.stage as ToastScoreKind, climb.row.last_price, nowMs);
  return true;
}

/** The hot list as read now: each auto star that just joined toasts once. Returns the symbols that toasted. */
export function noteHotListJoins(view: HotListView | null, nowMs: number = Date.now()): string[] {
  const shown: string[] = [];
  for (const { symbol, join } of freshJoins(view, nowMs)) {
    if (pass({ kind: 'join', symbol }, nowMs) !== 'raise') continue;
    publish(withWatchJoin(toasts, symbol, join, nowMs));
    recordToast(symbol, 'join', null, nowMs);
    shown.push(symbol);
  }
  return shown;
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
  gate = null;
  publish([]);
}
