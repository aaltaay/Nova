/** Recording truth comes exclusively from fresh /api/ibkr/status snapshots. */
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import {
  getIbkrStatusSnapshot,
  refreshIbkrStatusNow,
  subscribeIbkrStatus,
} from '../ibkr/ibkrStatusPoller';
import { CAPTURE_STATUS_FRESH_MS } from './constants';

type Listener = () => void;
const listeners = new Set<Listener>();
let unsubscribe: (() => void) | null = null;
let expiryTimer: ReturnType<typeof setTimeout> | null = null;
let commandError: string | null = null;
let lastLoggedError: string | null = null;

function publish(): void {
  listeners.forEach(listener => listener());
}

function fresh(): boolean {
  const status = getIbkrStatusSnapshot();
  return !status.stale && status.lastSuccessAt != null
    && Date.now() - status.lastSuccessAt < CAPTURE_STATUS_FRESH_MS;
}

export function getRecordingSymbols(): string[] {
  const status = getIbkrStatusSnapshot();
  const recordingSymbol = fresh() && status.capture === true && status.recording === true
    && typeof status.capture_symbol === 'string'
    ? status.capture_symbol.trim().toUpperCase() : null;
  return recordingSymbol ? [recordingSymbol] : [];
}

export function isTabRecording(symbol: string): boolean {
  return getRecordingSymbols()[0] === symbol.trim().toUpperCase();
}

export function getSessionRecordError(): string | null {
  const status = getIbkrStatusSnapshot();
  if (commandError) return commandError;
  if (status.stale) return 'Recording status unavailable; Nova status request failed';
  if (status.lastSuccessAt != null && !fresh()) return 'Recording status is stale';
  return status.capture_error || null;
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

async function toggleRecord(symbol: string, enabled: boolean): Promise<string | null> {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return 'No symbol';
  commandError = null;
  publish();
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, symbol: sym }),
    });
    const body = await res.json();
    if (!res.ok || body.error || body.capture !== enabled
      || (enabled && body.capture_symbol !== sym)) {
      commandError = (typeof body.error === 'string' && body.error)
        || (typeof body.detail === 'string' && body.detail)
        || `Record ${enabled ? 'start' : 'stop'} failed`;
    }
  } catch {
    commandError = `Could not reach Nova to ${enabled ? 'start' : 'stop'} recording`;
  }
  if (commandError) console.warn('session Record:', commandError);
  publish();
  // Even a failed request may have reached the server. Reconcile through the
  // shared poller; never infer success/ownership from the requested symbol.
  refreshIbkrStatusNow();
  return commandError;
}

export const startTabRecord = (symbol: string): Promise<string | null> => toggleRecord(symbol, true);
export const stopTabRecord = (symbol: string): Promise<string | null> => toggleRecord(symbol, false);
