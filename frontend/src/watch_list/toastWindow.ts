/**
 * The trading window the watch list's toasts come in (ADR 044 amendment, operator ask 2026-10-12): an Eastern
 * "HH:MM" start and end, set on the Hot list tab and kept in this desk's `localStorage`
 * (`nova.watch.toastWindow` = `{schema_version: 1, start, end}`). Every window of the desk shares it; another
 * window's change arrives by the `storage` event. An unknown version or a malformed window reads as the default
 * with a console warning, never a guess. Also the toasts' Eastern clock: the minute of the day, and the trading
 * day, which starts at 04:00 ET.
 */
import { useSyncExternalStore } from 'react';
import {
  WATCH_TOAST_WINDOW_BAD,
  WATCH_TOAST_WINDOW_DEFAULT,
  WATCH_TOAST_WINDOW_KEY,
  WATCH_TOAST_WINDOW_SCHEMA_VERSION,
} from './watchListConstants';

export interface ToastWindow {
  /** Eastern "HH:MM", inclusive. */
  start: string;
  /** Eastern "HH:MM", exclusive. */
  end: string;
}

const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;
const DEFAULT: ToastWindow = { ...WATCH_TOAST_WINDOW_DEFAULT };
/** The trading day starts at 04:00 ET: an instant this long earlier falls on its trading day's calendar date. */
const DAY_START_SHIFT_MS = 4 * 60 * 60_000;

const ET_MINUTE = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
});
const ET_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
});

/** Minutes since midnight, Eastern, at `ms`. */
export function etMinutesOf(ms: number): number {
  const parts = ET_MINUTE.formatToParts(new Date(ms));
  const hour = Number(parts.find(p => p.type === 'hour')?.value ?? '0') % 24;   // some engines say 24 at midnight
  return hour * 60 + Number(parts.find(p => p.type === 'minute')?.value ?? '0');
}

/** The trading day `ms` falls on, "YYYY-MM-DD": it starts at 04:00 ET. */
export function tradingDayOf(ms: number): string {
  return ET_DATE.format(new Date(ms - DAY_START_SHIFT_MS));
}

export function hhmmMinutes(text: string): number | null {
  const m = HHMM.exec(text);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** Why `w` is not a window, or null when it is one. */
export function toastWindowError(w: ToastWindow): string | null {
  const start = hhmmMinutes(w.start);
  const end = hhmmMinutes(w.end);
  if (start === null || end === null) return 'A time is HH:MM, Eastern';
  return end > start ? null : WATCH_TOAST_WINDOW_BAD;
}

export function inToastWindow(w: ToastWindow, etMinutes: number): boolean {
  const start = hhmmMinutes(w.start);
  const end = hhmmMinutes(w.end);
  return start !== null && end !== null && etMinutes >= start && etMinutes < end;
}

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function read(): ToastWindow {
  const store = storage();
  if (!store) return DEFAULT;
  try {
    const raw = store.getItem(WATCH_TOAST_WINDOW_KEY);
    if (!raw) return DEFAULT;
    const parsed = JSON.parse(raw) as { schema_version?: unknown; start?: unknown; end?: unknown };
    if (parsed.schema_version !== WATCH_TOAST_WINDOW_SCHEMA_VERSION) {
      console.warn('[nova] ignoring a toast window with unknown schema_version', parsed.schema_version);
      return DEFAULT;
    }
    const w = { start: String(parsed.start ?? ''), end: String(parsed.end ?? '') };
    if (toastWindowError(w)) {
      console.warn('[nova] ignoring a malformed toast window', parsed);
      return DEFAULT;
    }
    return w;
  } catch (err) {
    console.warn('[nova] unreadable toast window', err);
    return DEFAULT;
  }
}

let cached: ToastWindow | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach(fn => fn());
}

export function getToastWindow(): ToastWindow {
  if (cached === null) cached = read();
  return cached;
}

/** Saves `w`; the refusal in words when it is not a window (nothing is saved then). */
export function saveToastWindow(w: ToastWindow): string | null {
  const error = toastWindowError(w);
  if (error) return error;
  try {
    storage()?.setItem(WATCH_TOAST_WINDOW_KEY, JSON.stringify({ schema_version: WATCH_TOAST_WINDOW_SCHEMA_VERSION, ...w }));
  } catch (err) {
    console.warn('[nova] could not save the toast window', err);
    return 'This desk could not save it (browser storage refused)';
  }
  cached = { ...w };
  notify();
  return null;
}

export function resetToastWindow(): void {
  try {
    storage()?.removeItem(WATCH_TOAST_WINDOW_KEY);
  } catch (err) {
    console.warn('[nova] could not reset the toast window', err);
  }
  cached = DEFAULT;
  notify();
}

/** Whether a toast may come at `ms`. */
export function toastWindowOpen(ms: number): boolean {
  return inToastWindow(getToastWindow(), etMinutesOf(ms));
}

function onStorage(event: StorageEvent): void {
  if (event.key !== WATCH_TOAST_WINDOW_KEY) return;
  cached = null;
  notify();
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  if (listeners.size === 1 && typeof window !== 'undefined') window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(fn);
    if (listeners.size === 0 && typeof window !== 'undefined') window.removeEventListener('storage', onStorage);
  };
}

export function useToastWindow(): ToastWindow {
  return useSyncExternalStore(subscribe, getToastWindow, getToastWindow);
}

/** Test-only. */
export function resetToastWindowForTests(): void {
  cached = null;
}
