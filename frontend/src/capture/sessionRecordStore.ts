/** Client store: which trader tabs are recording IBKR sessions. */
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';

type Listener = () => void;

const recording = new Set<string>();
const listeners = new Set<Listener>();
let hydrated = false;

function publish(): void {
  listeners.forEach(l => l());
}

export function isTabRecording(symbol: string): boolean {
  return recording.has(symbol.trim().toUpperCase());
}

export function getRecordingSymbols(): string[] {
  return [...recording];
}

export function subscribeSessionRecord(listener: Listener): () => void {
  listeners.add(listener);
  if (!hydrated) {
    hydrated = true;
    void hydrateFromApi();
  }
  return () => listeners.delete(listener);
}

async function hydrateFromApi(): Promise<void> {
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/capture`);
    if (!res.ok) return;
    const body = await res.json();
    recording.clear();
    if (body.capture && body.capture_symbol) {
      recording.add(String(body.capture_symbol).toUpperCase());
    }
    publish();
  } catch {
    /* ignore */
  }
}

export async function startTabRecord(symbol: string): Promise<string | null> {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return 'No symbol';
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: true, symbol: sym }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || body.capture !== true) {
      return (
        (typeof body.error === 'string' && body.error) ||
        (typeof body.detail === 'string' && body.detail) ||
        'Record start failed'
      );
    }
    recording.add(sym);
    publish();
    return null;
  } catch {
    return 'Could not reach Nova to start recording';
  }
}

export async function stopTabRecord(symbol: string): Promise<string | null> {
  const sym = symbol.trim().toUpperCase();
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: false, symbol: sym }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return (typeof body.detail === 'string' && body.detail) || 'Record stop failed';
    }
    recording.delete(sym);
    publish();
    return null;
  } catch {
    return 'Could not reach Nova to stop recording';
  }
}
