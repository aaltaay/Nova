/**
 * Nova scores its own toasts (ADR 044 amendment, operator ask 2026-10-12), so whether they are useful is a number
 * on the Hot list tab and not a feeling. Every toast raised today is kept with its kind, time and the price it
 * showed. Once its five minutes have passed, the main desk window reads the symbol's live 1-minute bars: the
 * reference is the toast's price (else the close of the last minute before it), the outcome the close of the
 * fifth minute after the toast's own. A replay answer or a failed read is tried again; after
 * WATCH_TOAST_SCORE_GIVE_UP_MS the toast reads "no bars", never a guess. Events the gate held back are counted by
 * reason beside them.
 *
 * The day's record is this desk's `localStorage` `nova.watch.toastScores` (schema in
 * `architecture/schema/desk-ops.md`), replaced at the next trading day (04:00 ET); an unknown version is dropped
 * with a console warning. Another window reads it by the `storage` event. A score is not a fill.
 */
import { useSyncExternalStore } from 'react';
import { API_URL } from '../constants';
import type { HeldReason } from './toastGate';
import { tradingDayOf } from './toastWindow';
import {
  WATCH_TOAST_SCORE_GIVE_UP_MS,
  WATCH_TOAST_SCORE_MINUTES,
  WATCH_TOAST_SCORE_NO_BARS,
  WATCH_TOAST_SCORE_SETTLE_MS,
  WATCH_TOAST_SCORE_TIMEFRAME,
  WATCH_TOAST_SCORES_KEY,
  WATCH_TOAST_SCORES_MAX,
  WATCH_TOAST_SCORES_SCHEMA_VERSION,
} from './watchListConstants';

export type ToastScoreKind = 'join' | 'hod' | 'armed' | 'near' | 'triggered';
export const TOAST_SCORE_KINDS: readonly ToastScoreKind[] = ['join', 'hod', 'armed', 'near', 'triggered'];

/** `move` is a fraction: `after / ref - 1`. `none` says why there is no score. */
export type ToastScore = { ref: number; after: number; move: number } | { none: string };

export interface ToastRecord {
  id: string;
  symbol: string;
  kind: ToastScoreKind;
  /** When it was raised, epoch ms. */
  at: number;
  /** The price the toast showed; null when it showed none. */
  price: number | null;
  score: ToastScore | null;
}

export interface ToastScoresDoc {
  schema_version: number;
  day: string;
  toasts: ToastRecord[];
  held: Partial<Record<HeldReason, number>>;
}

/** One 1-minute bar: `t` the minute's start, epoch seconds. */
export interface MinuteBar {
  t: number;
  c: number;
}

export interface BarsRead {
  bars: MinuteBar[];
  /** The desk answered from a Sim replay: not today's live tape, so not a score. */
  replay: boolean;
}

const MINUTE_S = 60;

function toastMinute(at: number): number {
  return Math.floor(at / 60_000) * MINUTE_S;
}

function lastMinute(at: number): number {
  return toastMinute(at) + WATCH_TOAST_SCORE_MINUTES * MINUTE_S;
}

/** Whether `record`'s fifth minute has closed and settled, so its bars are final. */
export function dueForScore(record: ToastRecord, nowMs: number): boolean {
  return record.score === null && nowMs >= (lastMinute(record.at) + MINUTE_S) * 1000 + WATCH_TOAST_SCORE_SETTLE_MS;
}

/**
 * Pure: `record`'s score from its symbol's 1-minute bars, or null to try again: while the bars do not reach back
 * to the toast, or not yet to its fifth minute (IBKR's history can lag the tape). `final` (the last try) scores
 * with what there is: no trade since means the last close still stands. Every price is a bar's close: the minute
 * before the toast when the toast showed none, and the last minute at or before the fifth after the toast's own.
 */
export function scoreFromBars(record: ToastRecord, bars: readonly MinuteBar[], final = false): ToastScore | null {
  const start = toastMinute(record.at);
  const end = lastMinute(record.at);
  const sorted = bars.filter(b => Number.isFinite(b.t) && Number.isFinite(b.c) && b.c > 0).sort((a, b) => a.t - b.t);
  if (!sorted.some(b => b.t <= start)) return final ? { none: WATCH_TOAST_SCORE_NO_BARS } : null;
  if (!final && !sorted.some(b => b.t >= end)) return null;
  const before = [...sorted].reverse().find(b => b.t < start);
  const ref = record.price != null && Number.isFinite(record.price) && record.price > 0 ? record.price : before?.c;
  if (ref == null) return { none: WATCH_TOAST_SCORE_NO_BARS };
  const after = [...sorted].reverse().find(b => b.t <= end);
  if (!after) return { none: WATCH_TOAST_SCORE_NO_BARS };
  return { ref, after: after.c, move: after.c / ref - 1 };
}

export interface KindSummary {
  kind: ToastScoreKind;
  toasts: number;
  /** Toasts with a move. */
  scored: number;
  /** Scored toasts whose price was higher five minutes later. */
  higher: number;
  /** The median move of the scored toasts (a fraction); null with none scored. */
  medianMove: number | null;
}

function median(values: readonly number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** Pure: the day per kind, in the kinds' order, leaving out kinds with no toast. */
export function summarizeToasts(doc: ToastScoresDoc): KindSummary[] {
  return TOAST_SCORE_KINDS.flatMap(kind => {
    const of = doc.toasts.filter(t => t.kind === kind);
    if (!of.length) return [];
    const moves = of.flatMap(t => (t.score && 'move' in t.score ? [t.score.move] : []));
    return [{ kind, toasts: of.length, scored: moves.length, higher: moves.filter(m => m > 0).length, medianMove: median(moves) }];
  });
}

/* ---------- the day's record ---------- */

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function empty(day: string): ToastScoresDoc {
  return { schema_version: WATCH_TOAST_SCORES_SCHEMA_VERSION, day, toasts: [], held: {} };
}

function load(day: string): ToastScoresDoc {
  const store = storage();
  if (!store) return empty(day);
  try {
    const raw = store.getItem(WATCH_TOAST_SCORES_KEY);
    if (!raw) return empty(day);
    const parsed = JSON.parse(raw) as Partial<ToastScoresDoc>;
    if (parsed.schema_version !== WATCH_TOAST_SCORES_SCHEMA_VERSION) {
      console.warn('[nova] dropping toast scores with unknown schema_version', parsed.schema_version);
      return empty(day);
    }
    if (parsed.day !== day || !Array.isArray(parsed.toasts)) return empty(day);
    return { schema_version: WATCH_TOAST_SCORES_SCHEMA_VERSION, day, toasts: parsed.toasts, held: parsed.held ?? {} };
  } catch (err) {
    console.warn('[nova] unreadable toast scores', err);
    return empty(day);
  }
}

let doc: ToastScoresDoc | null = null;
const listeners = new Set<() => void>();
let saveTimer: ReturnType<typeof setTimeout> | null = null;

function current(nowMs: number): ToastScoresDoc {
  const day = tradingDayOf(nowMs);
  if (doc === null || doc.day !== day) doc = load(day);
  return doc;
}

function save(): void {
  if (saveTimer !== null) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  if (!doc) return;
  try {
    storage()?.setItem(WATCH_TOAST_SCORES_KEY, JSON.stringify(doc));
  } catch (err) {
    console.warn('[nova] could not save the toast scores', err);
  }
}

function publish(next: ToastScoresDoc, now: 'now' | 'soon'): void {
  doc = next;
  listeners.forEach(fn => fn());
  if (now === 'now') save();
  else if (saveTimer === null) saveTimer = setTimeout(save, 2_000);    // held counts come in bursts
}

/** A toast was raised: keep it for scoring. */
export function recordToast(symbol: string, kind: ToastScoreKind, price: number | null, nowMs: number = Date.now()): void {
  const day = current(nowMs);
  const record: ToastRecord = {
    id: `${symbol}-${kind}-${nowMs}`, symbol, kind, at: nowMs,
    price: price != null && Number.isFinite(price) && price > 0 ? price : null, score: null,
  };
  publish({ ...day, toasts: [...day.toasts, record].slice(-WATCH_TOAST_SCORES_MAX) }, 'now');
}

/** The gate held an event back. */
export function recordHeld(reason: HeldReason, nowMs: number = Date.now()): void {
  const day = current(nowMs);
  publish({ ...day, held: { ...day.held, [reason]: (day.held[reason] ?? 0) + 1 } }, 'soon');
}

/** The live 1-minute bars of `symbol`, the newest `limit`. */
export async function fetchMinuteBars(symbol: string, limit: number): Promise<BarsRead> {
  const params = new URLSearchParams({ timeframe: WATCH_TOAST_SCORE_TIMEFRAME, limit: String(limit) });
  const res = await fetch(`${API_URL}/ticker/${encodeURIComponent(symbol)}/bars?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as { bars?: Array<{ t?: unknown; c?: unknown }>; coverage?: { replay?: unknown } };
  const bars = (data.bars ?? []).flatMap(b => {
    const t = typeof b.t === 'string' ? Date.parse(b.t) / 1000 : typeof b.t === 'number' ? b.t : NaN;
    return Number.isFinite(t) && typeof b.c === 'number' ? [{ t, c: b.c }] : [];
  });
  return { bars, replay: Boolean(data.coverage?.replay) };
}

let scoring = false;

/** Score every toast whose five minutes have passed: one bars read per symbol. */
export async function scorePendingToasts(
  nowMs: number = Date.now(),
  read: (symbol: string, limit: number) => Promise<BarsRead> = fetchMinuteBars,
): Promise<void> {
  if (scoring) return;
  const due = current(nowMs).toasts.filter(t => dueForScore(t, nowMs));
  if (!due.length) return;
  scoring = true;
  try {
    const scores = new Map<string, ToastScore>();
    for (const symbol of new Set(due.map(t => t.symbol))) {
      const mine = due.filter(t => t.symbol === symbol);
      const oldest = Math.min(...mine.map(t => t.at));
      const limit = Math.min(1_000, Math.max(30, Math.ceil((nowMs - oldest) / 60_000) + 15));
      let got: BarsRead | null = null;
      try {
        got = await read(symbol, limit);
      } catch (err) {
        console.warn('[nova] toast scores: the bars of', symbol, 'could not be read', err);
      }
      for (const t of mine) {
        const final = nowMs - t.at > WATCH_TOAST_SCORE_GIVE_UP_MS;
        const score = got && !got.replay ? scoreFromBars(t, got.bars, final) : null;
        if (score) scores.set(t.id, score);
        else if (final) scores.set(t.id, { none: WATCH_TOAST_SCORE_NO_BARS });
      }
    }
    if (!scores.size) return;
    const day = current(nowMs);
    publish({ ...day, toasts: day.toasts.map(t => (scores.has(t.id) ? { ...t, score: scores.get(t.id)! } : t)) }, 'now');
  } finally {
    scoring = false;
  }
}

export function getToastScores(): ToastScoresDoc {
  return current(Date.now());
}

function onStorage(event: StorageEvent): void {
  if (event.key !== WATCH_TOAST_SCORES_KEY) return;
  doc = null;
  listeners.forEach(fn => fn());
}

export function subscribeToastScores(fn: () => void): () => void {
  listeners.add(fn);
  if (listeners.size === 1 && typeof window !== 'undefined') window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(fn);
    if (listeners.size === 0 && typeof window !== 'undefined') window.removeEventListener('storage', onStorage);
  };
}

export function useToastScores(): ToastScoresDoc {
  return useSyncExternalStore(subscribeToastScores, getToastScores, getToastScores);
}

/** Test-only: forget the record in memory (the test clears localStorage itself). */
export function resetToastScoresForTests(): void {
  if (saveTimer !== null) clearTimeout(saveTimer);
  saveTimer = null;
  doc = null;
  scoring = false;
}
