/**
 * Pure helpers for IBKR Time & Sales feed handling.
 * Kept out of the React hook so symbol-gating and clear-on-switch are unit-testable.
 */
import { TAPE_UI_MAX_ROWS } from '../constants';
import type { LineLent } from './lentWords';

export type TapeSide = 'ask' | 'bid' | 'between' | 'unknown';

export interface TapePrint {
  /** Stable canonical replay print identity; absent for the live feed. */
  replayId?: string;
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
  /** IBKR tickAttribLast.unreported: listed, but not in candles/last/volume. */
  unreported?: boolean;
  /**
   * False for a print reported for volume only (odd lot, average price, ...):
   * the backend's `sets_price` (AGENTS.md §3). Absent reads as a price.
   */
  setsPrice?: boolean;
}

export type TapeSilenceRecoveryState =
  | 'holding'
  | 'delegated'
  | 'waiting'
  | 'attempting'
  | 'failed'
  | 'resumed';

export interface TapeSilenceRecovery {
  state: TapeSilenceRecoveryState;
  since: number;
  askedAt: number | null;
  text: string;
}

/**
 * The backend's word on a live line with no print for a while (#722; backend `ibkr/tape_silence.py`),
 * carried by the socket's idle `ping`: halted (a halt prints nothing), silent (no print while Level 2
 * kept updating: the line may be down) or quiet (the book is quiet too). Any print clears it.
 */
export interface TapeSilence {
  state: 'halted' | 'dead' | 'silent' | 'quiet';
  /** Epoch seconds the silence counts from: the last print, the line's opening or the reopening. */
  since: number;
  text: string;
  /**
   * The other live lines in the same silence (dead or silent only): IBKR's tape stopped, not this line
   * (2026-10-13 07:59:22 ET, every line at once). Empty or absent when none, or from an older backend.
   */
  pipeline?: string[];
  /**
   * Bounded recovery outcome on a registered-dead line (#722); absent when no silence recovery watch is active.
   */
  recovery?: TapeSilenceRecovery;
}

const SILENCE_STATES = new Set(['halted', 'dead', 'silent', 'quiet']);
const SILENCE_RECOVERY_STATES = new Set<TapeSilenceRecoveryState>([
  'holding',
  'delegated',
  'waiting',
  'attempting',
  'failed',
  'resumed',
]);

function parseTapeSilenceRecovery(raw: unknown): TapeSilenceRecovery | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.state !== 'string' || !SILENCE_RECOVERY_STATES.has(r.state as TapeSilenceRecoveryState)) return null;
  if (typeof r.since !== 'number' || !Number.isFinite(r.since) || typeof r.text !== 'string') return null;
  const askedAt = typeof r.asked_at === 'number' && Number.isFinite(r.asked_at) ? r.asked_at : null;
  return {
    state: r.state as TapeSilenceRecoveryState,
    since: r.since,
    askedAt,
    text: r.text,
  };
}

/** A ping's `silence`, or null for anything else (no reading, an older backend, a broken frame). */
export function parseTapeSilence(raw: unknown): TapeSilence | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.state !== 'string' || !SILENCE_STATES.has(r.state)) return null;
  if (typeof r.since !== 'number' || !Number.isFinite(r.since) || typeof r.text !== 'string') return null;
  const pipeline = Array.isArray(r.pipeline) ? r.pipeline.filter((s): s is string => typeof s === 'string') : [];
  const recovery = parseTapeSilenceRecovery(r.recovery);
  return {
    state: r.state as TapeSilence['state'],
    since: r.since,
    text: r.text,
    pipeline,
    ...(recovery ? { recovery } : {}),
  };
}

/**
 * Apply a non-fatal registered-silent recovery frame (#722) to the hook's current silence state.
 * Works even when a viewer socket receives the broadcast recovery frame before its first silence ping.
 */
export function applyTapeSilentRecoveryFrame(
  current: TapeSilence | null,
  msg: Record<string, unknown>,
  nowSec: number = Math.floor(Date.now() / 1000),
): TapeSilence | null {
  const state = msg.silent_recovery;
  if (typeof state !== 'string' || !SILENCE_RECOVERY_STATES.has(state as TapeSilenceRecoveryState)) {
    return null;
  }
  const recText = typeof msg.message === 'string' ? msg.message : '';
  if (current != null) {
    const baseText =
      current.recovery?.text && current.text.endsWith(` ${current.recovery.text}`)
        ? current.text.slice(0, -(current.recovery.text.length + 1))
        : current.text;
    return {
      ...current,
      text: recText && !baseText.endsWith(recText) ? `${baseText} ${recText}` : baseText,
      recovery: {
        state: state as TapeSilenceRecoveryState,
        since: current.since,
        askedAt: current.recovery?.askedAt ?? null,
        text: recText,
      },
    };
  }
  const since =
    typeof msg.silence_since === 'number' && Number.isFinite(msg.silence_since) && msg.silence_since > 0
      ? msg.silence_since
      : nowSec;
  return {
    state: 'dead',
    since,
    text: recText,
    pipeline: [],
    recovery: {
      state: state as TapeSilenceRecoveryState,
      since,
      askedAt: null,
      text: recText,
    },
  };
}

export interface TapeState {
  prints: TapePrint[];
  connected: boolean;
  error: string | null;
  /**
   * The live line is lent to one of Nova's setups with the tab's Level 2 (ADR 044 decision 6):
   * the pane says whose and when it comes back. Absent or null for every other feed.
   */
  lent?: LineLent | null;
  /**
   * IBKR refused or ended the line and the backend asks again at this moment (epoch seconds, #698):
   * the pane says RETRYING, not ERROR. Absent or null otherwise.
   */
  retryAt?: number | null;
  /** The line has printed nothing for a while (#722); absent or null while it prints. */
  silence?: TapeSilence | null;
}

/** A print that may set a price: not flagged unreported, and not volume-only by its conditions. */
export function tapePrintSetsPrice(print: Pick<TapePrint, 'unreported' | 'setsPrice'>): boolean {
  return !print.unreported && print.setsPrice !== false;
}

/** Uppercase symbol key, or null when no subscription. */
export function tapeSymbolKey(symbol: string | null): string | null {
  return symbol ? symbol.toUpperCase() : null;
}

/** Fresh empty tape — used on mount and immediately on symbol change. */
export function emptyTapeState(): TapeState {
  return { prints: [], connected: false, error: null, lent: null, retryAt: null, silence: null };
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

/**
 * Apply a burst of AllLast prints in arrival order. Newest ends up first.
 * Does not invent prints; the ring cap may drop the oldest, same as live.
 */
export function flushPendingTapePrints(
  prints: TapePrint[],
  pending: TapePrint[],
  maxRows: number = TAPE_UI_MAX_ROWS,
): TapePrint[] {
  if (pending.length === 0) return prints;
  let next = prints;
  for (const print of pending) {
    next = appendTapePrint(next, print, maxRows);
  }
  return next;
}
