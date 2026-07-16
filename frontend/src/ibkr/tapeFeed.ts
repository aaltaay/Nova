/**
 * Pure helpers for IBKR Time & Sales feed handling.
 * Kept out of the React hook so symbol-gating and clear-on-switch are unit-testable.
 */
import { TAPE_UI_MAX_ROWS } from '../constants';

export type TapeSide = 'ask' | 'bid' | 'between' | 'unknown';

export interface TapePrint {
  symbol: string;
  time: string;
  price: number;
  size: number;
  exchange: string;
  conditions?: string;
  /** Aggressor vs BBO at print time: ask | bid | between | unknown */
  side?: TapeSide;
  bid?: number | null;
  ask?: number | null;
}

export interface TapeState {
  prints: TapePrint[];
  connected: boolean;
  error: string | null;
}

/** Uppercase symbol key, or null when no subscription. */
export function tapeSymbolKey(symbol: string | null): string | null {
  return symbol ? symbol.toUpperCase() : null;
}

/** Fresh empty tape — used on mount and immediately on symbol change. */
export function emptyTapeState(): TapeState {
  return { prints: [], connected: false, error: null };
}

/**
 * Symbol gate: ignore WS messages whose symbol does not match the hook's current key.
 * Messages without a string symbol are allowed through (e.g. some error frames).
 */
export function tapeMessageAllowed(msgSymbol: unknown, currentSymKey: string): boolean {
  if (typeof msgSymbol !== 'string') return true;
  return msgSymbol.toUpperCase() === currentSymKey;
}

/** Prepend a print and cap at maxRows (newest first). */
export function appendTapePrint(
  prints: TapePrint[],
  print: TapePrint,
  maxRows: number = TAPE_UI_MAX_ROWS,
): TapePrint[] {
  const next = [print, ...prints];
  return next.length > maxRows ? next.slice(0, maxRows) : next;
}
