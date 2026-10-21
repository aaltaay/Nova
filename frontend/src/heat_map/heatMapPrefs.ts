/**
 * The heat map's saved choices (ADR 061): whether it replaces the Trader's charts, the window across the screen, the
 * smallest burst that gets a dot, and the brightness. One set for every Trader tab and window, kept across restarts
 * in `localStorage[HEAT_PREFS_KEY]` as `{schema_version: 1, shown, windowSec, minDot, brightness}`; another
 * window's change arrives through the `storage` event. An unreadable or unknown version reads as the defaults.
 */
import { useSyncExternalStore } from 'react';
import {
  HEAT_BRIGHTNESS_DEFAULT,
  HEAT_DOT_MIN_DEFAULT,
  HEAT_DOT_MIN_OPTIONS,
  HEAT_PREFS_KEY,
  HEAT_PREFS_VERSION,
  HEAT_WINDOW_DEFAULT_SEC,
  HEAT_WINDOW_MAX_SEC,
  HEAT_WINDOW_MIN_SEC,
} from './heatMapConstants';

export interface HeatPrefs {
  shown: boolean;
  windowSec: number;
  minDot: number;
  brightness: number;
}

export const HEAT_PREFS_DEFAULT: HeatPrefs = {
  shown: false,
  windowSec: HEAT_WINDOW_DEFAULT_SEC,
  minDot: HEAT_DOT_MIN_DEFAULT,
  brightness: HEAT_BRIGHTNESS_DEFAULT,
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** A stored value as prefs: anything missing, malformed or of another version reads as the default. */
export function parseHeatPrefs(raw: string | null): HeatPrefs {
  if (!raw) return HEAT_PREFS_DEFAULT;
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v.schema_version !== HEAT_PREFS_VERSION) return HEAT_PREFS_DEFAULT;
    const num = (x: unknown, d: number) => (typeof x === 'number' && Number.isFinite(x) ? x : d);
    const minDot = num(v.minDot, HEAT_DOT_MIN_DEFAULT);
    return {
      shown: v.shown === true,
      windowSec: clamp(num(v.windowSec, HEAT_WINDOW_DEFAULT_SEC), HEAT_WINDOW_MIN_SEC, HEAT_WINDOW_MAX_SEC),
      minDot: (HEAT_DOT_MIN_OPTIONS as readonly number[]).includes(minDot) ? minDot : HEAT_DOT_MIN_DEFAULT,
      brightness: clamp(num(v.brightness, HEAT_BRIGHTNESS_DEFAULT), 0, 100),
    };
  } catch {
    return HEAT_PREFS_DEFAULT;
  }
}

const listeners = new Set<() => void>();

function read(): HeatPrefs {
  try {
    return parseHeatPrefs(localStorage.getItem(HEAT_PREFS_KEY));
  } catch {
    return HEAT_PREFS_DEFAULT;
  }
}

let prefs = read();

function emit(): void {
  for (const l of listeners) l();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== HEAT_PREFS_KEY) return;
    prefs = read();
    emit();
  });
}

export function setHeatPrefs(patch: Partial<HeatPrefs>): void {
  prefs = parseHeatPrefs(JSON.stringify({ schema_version: HEAT_PREFS_VERSION, ...prefs, ...patch }));
  try {
    localStorage.setItem(HEAT_PREFS_KEY, JSON.stringify({ schema_version: HEAT_PREFS_VERSION, ...prefs }));
  } catch {
    /* storage refused (the sample desk): the choice lasts this session */
  }
  emit();
}

export function heatPrefs(): HeatPrefs {
  return prefs;
}

export function useHeatPrefs(): HeatPrefs {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => prefs,
  );
}

/** Tests only: read storage again. */
export function reloadHeatPrefsForTests(): void {
  prefs = read();
  emit();
}
