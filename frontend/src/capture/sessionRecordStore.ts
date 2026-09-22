/** Recording truth comes exclusively from fresh /api/ibkr/status snapshots. */
import { useSyncExternalStore } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import {
  getIbkrStatusSnapshot,
  refreshIbkrStatusNow,
  subscribeIbkrStatus,
} from '../ibkr/ibkrStatusPoller';
import { CAPTURE_COMMAND_PLAIN_ERROR_MAX_CHARS, CAPTURE_STATUS_FRESH_MS } from './constants';

type Listener = () => void;
const listeners = new Set<Listener>();
let unsubscribe: (() => void) | null = null;
let expiryTimer: ReturnType<typeof setTimeout> | null = null;
/** The last Record command's failure, per symbol: B's menu never shows A's (C55). */
const commandErrors = new Map<string, string>();
let lastCommandError: string | null = null;
let lastLoggedError: string | null = null;

// Bumped on every publish: a snapshot for useSyncExternalStore that changes
// when anything here changes (a dismissal, a command error), not only when
// the status object does.
let version = 0;

function publish(): void {
  version += 1;
  listeners.forEach(listener => listener());
}

export function getSessionRecordVersion(): number {
  return version;
}

function fresh(): boolean {
  const status = getIbkrStatusSnapshot();
  return !status.stale && status.lastSuccessAt != null
    && Date.now() - status.lastSuccessAt < CAPTURE_STATUS_FRESH_MS;
}

/**
 * The symbols a payload says are recording; an older payload names one. Only
 * a list of strings counts -- `capture_symbols: "GRML"` used to take the Desk
 * page down (QA 2026-09-22, C14).
 */
export function recordingSymbolsIn(status: { capture_symbols?: unknown; capture_symbol?: unknown }): string[] {
  const list: unknown[] = Array.isArray(status.capture_symbols)
    ? status.capture_symbols
    : typeof status.capture_symbol === 'string' ? [status.capture_symbol] : [];
  return list
    .filter((value): value is string => typeof value === 'string')
    .map(value => value.trim().toUpperCase())
    .filter(Boolean);
}

/** Recording symbols from a fresh status only; a stale snapshot records nothing (C23). */
export function getRecordingSymbols(): string[] {
  const status = getIbkrStatusSnapshot();
  if (!fresh() || status.capture !== true || status.recording !== true) return [];
  return recordingSymbolsIn(status);
}

/** The fresh, guarded recording symbols as a hook -- what the rail, Desk and Records should read. */
export function useRecordingSymbols(): string[] {
  useSyncExternalStore(subscribeSessionRecord, getSessionRecordVersion);
  return getRecordingSymbols();
}

export function isTabRecording(symbol: string): boolean {
  return getRecordingSymbols().includes(symbol.trim().toUpperCase());
}

/** `capture_errors` (per symbol) when the backend sends it; null from an older backend. */
function perSymbolErrors(status: object): Record<string, unknown> | null {
  const errors = (status as { capture_errors?: unknown }).capture_errors;
  return errors && typeof errors === 'object' && !Array.isArray(errors) ? errors as Record<string, unknown> : null;
}

/**
 * Why Record is not working. With a symbol: that symbol's own command failure
 * or recorder / tape trouble -- never another recording's (C55). Without one:
 * the legacy single value. Status freshness is shared by every symbol.
 */
export function getSessionRecordError(symbol?: string): string | null {
  const status = getIbkrStatusSnapshot();
  const sym = symbol?.trim().toUpperCase() || null;
  const command = sym ? commandErrors.get(sym) ?? null : lastCommandError;
  if (command) return command;
  if (status.stale) return 'Recording status unavailable; Nova status request failed';
  if (status.lastSuccessAt != null && !fresh()) return 'Recording status is stale';
  const errors = sym ? perSymbolErrors(status) : null;
  if (errors) {
    const own = errors[sym!];
    return typeof own === 'string' && own ? own : null;
  }
  return typeof status.capture_error === 'string' && status.capture_error ? status.capture_error : null;
}

function onStatus(): void {
  if (expiryTimer != null) clearTimeout(expiryTimer);
  expiryTimer = null;
  const status = getIbkrStatusSnapshot();
  if (fresh() && status.lastSuccessAt != null) {
    expiryTimer = setTimeout(onStatus, Math.max(0,
      status.lastSuccessAt + CAPTURE_STATUS_FRESH_MS - Date.now()));
  }
  const error = getSessionRecordError();
  if (error && error !== lastLoggedError) console.warn('session Record:', error);
  lastLoggedError = error;
  publish();
}

export function subscribeSessionRecord(listener: Listener): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    unsubscribe = subscribeIbkrStatus(onStatus);
    onStatus();
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      unsubscribe?.();
      unsubscribe = null;
      if (expiryTimer != null) clearTimeout(expiryTimer);
      expiryTimer = null;
    }
  };
}

/** The reply as JSON, or its raw text when it is not JSON (a Starlette 500 is text/plain). */
async function readReply(res: Response): Promise<{ body: Record<string, unknown> | null; text: string }> {
  if (typeof res.text === 'function') {
    const text = await res.text().catch(() => '');
    try {
      const body = JSON.parse(text);
      return { body: body && typeof body === 'object' && !Array.isArray(body) ? body : null, text };
    } catch {
      return { body: null, text };
    }
  }
  const body = await res.json().catch(() => null);
  return { body: body && typeof body === 'object' && !Array.isArray(body) ? body : null, text: '' };
}

/** "Nova answered 500: Internal Server Error" -- the server was reached, so never "could not reach" (C65). */
function answeredError(res: Response, text: string, enabled: boolean): string {
  const plain = text.trim();
  const quote = plain && plain.length <= CAPTURE_COMMAND_PLAIN_ERROR_MAX_CHARS && !plain.startsWith('<') ? `: ${plain}` : '';
  return res.ok
    ? `Nova sent an unreadable reply to Record ${enabled ? 'start' : 'stop'}`
    : `Nova answered ${res.status || 'an error'} to Record ${enabled ? 'start' : 'stop'}${quote}`;
}

async function toggleRecord(symbol: string, enabled: boolean): Promise<string | null> {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return 'No symbol';
  let error: string | null = null;
  commandErrors.delete(sym);
  lastCommandError = null;
  publish();
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, symbol: sym }),
    });
    const { body, text } = await readReply(res);
    if (body == null) {
      error = answeredError(res, text, enabled);
    } else {
      // Success is about THIS symbol: other symbols may keep recording.
      const recording = recordingSymbolsIn(body).includes(sym);
      if (!res.ok || body.error || recording !== enabled) {
        error = (typeof body.error === 'string' && body.error)
          || (typeof body.detail === 'string' && body.detail)
          || `Record ${enabled ? 'start' : 'stop'} failed`;
      }
    }
  } catch {
    error = `Could not reach Nova to ${enabled ? 'start' : 'stop'} recording`;
  }
  if (error) {
    commandErrors.set(sym, error);
    lastCommandError = error;
    console.warn('session Record:', error);
  }
  publish();
  // Even a failed request may have reached the server. Reconcile through the
  // shared poller; never infer success/ownership from the requested symbol.
  refreshIbkrStatusNow();
  return error;
}

export const startTabRecord = (symbol: string): Promise<string | null> => toggleRecord(symbol, true);
export const stopTabRecord = (symbol: string): Promise<string | null> => toggleRecord(symbol, false);

// The stop toast is per stop (symbol + when): dismissing one never hides the next.
const dismissedStops = new Set<string>();

export function dismissRecordingStop(key: string): void {
  dismissedStops.add(key);
  publish();
}

export function isRecordingStopDismissed(key: string): boolean {
  return dismissedStops.has(key);
}

/** Test seam. */
export function _resetSessionRecordStoreForTests(): void {
  dismissedStops.clear();
  commandErrors.clear();
  lastCommandError = null;
  lastLoggedError = null;
}
