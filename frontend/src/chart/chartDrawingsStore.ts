/**
 * ADR 015 — one set of drawings per symbol, shared by every chart pane.
 *
 * Each `TickerChart` builds its own `DrawingManager`, so before this store the
 * 1Min pane, 1Day pane, and Quote Panel chart each held a private set: a level
 * drawn on one was invisible on the others. This module is the single source of
 * truth those managers hydrate from and write back to.
 *
 * Mirrors `barsStore.ts`: module-level map, per-key listeners, deduped fetch.
 * Writes are debounced into one `PUT` so dragging an anchor (one
 * `drawing:updated` per mousemove) does not hammer the API.
 */
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import {
  API_BASE_URL,
  CHART_DRAWINGS_BROADCAST_CHANNEL,
  CHART_DRAWINGS_MAX_PER_SYMBOL,
  CHART_DRAWINGS_SAVE_DEBOUNCE_MS,
} from '../constants';
import { novaFetch } from '../api/novaFetch';

const API_URL = `${API_BASE_URL}/api`;

type Listener = () => void;

const drawings = new Map<string, SerializedDrawing[]>();
const listeners = new Map<string, Set<Listener>>();
const inflight = new Map<string, Promise<SerializedDrawing[]>>();
const saveTimers = new Map<string, ReturnType<typeof setTimeout>>();
/**
 * Bumped on every local change. A pane records the revision it produced so it
 * can tell its own echo from a real edit in a sibling pane -- without it, the
 * pane that just placed a line would immediately wipe and re-import it.
 */
const revisions = new Map<string, number>();

export function drawingsKey(symbol: string): string {
  return symbol.trim().toUpperCase();
}

function notify(key: string): void {
  const set = listeners.get(key);
  if (!set) return;
  for (const cb of [...set]) cb();
}

/** Cross-window fan-out: a detached Trader window is a separate renderer. */
let channel: BroadcastChannel | null = null;

function getChannel(): BroadcastChannel | null {
  if (channel) return channel;
  if (typeof BroadcastChannel === 'undefined') return null;
  try {
    channel = new BroadcastChannel(CHART_DRAWINGS_BROADCAST_CHANNEL);
    channel.onmessage = (event: MessageEvent) => {
      const symbol = (event.data as { symbol?: string } | null)?.symbol;
      if (typeof symbol !== 'string') return;
      // Trust the backend, not the message body -- refetch the authoritative list.
      void refreshDrawings(symbol);
    };
  } catch {
    channel = null;
  }
  return channel;
}

function announce(key: string): void {
  try {
    getChannel()?.postMessage({ symbol: key });
  } catch {
    // A closed channel must never break the local paint.
  }
}

export function getDrawings(symbol: string): SerializedDrawing[] {
  return drawings.get(drawingsKey(symbol)) ?? [];
}

export function subscribeDrawings(symbol: string, listener: Listener): () => void {
  const key = drawingsKey(symbol);
  let set = listeners.get(key);
  if (!set) {
    set = new Set();
    listeners.set(key, set);
  }
  set.add(listener);
  return () => {
    set!.delete(listener);
    if (set!.size === 0) listeners.delete(key);
  };
}

/** Monotonic change counter for a symbol's list. */
export function revisionOf(symbol: string): number {
  return revisions.get(drawingsKey(symbol)) ?? 0;
}

function sameList(a: readonly SerializedDrawing[], b: readonly SerializedDrawing[]): boolean {
  return a.length === b.length && JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Bumping the revision is what makes panes rebuild, so only bump on a real
 * change. A no-op bump (e.g. a GET returning the list we already hold) would
 * wipe and re-import every pane and drop the operator's selection for nothing.
 */
function setLocal(key: string, next: SerializedDrawing[]): void {
  if (sameList(drawings.get(key) ?? [], next)) return;
  if (next.length === 0) drawings.delete(key);
  else drawings.set(key, next);
  revisions.set(key, (revisions.get(key) ?? 0) + 1);
  notify(key);
}

async function fetchDrawings(key: string): Promise<SerializedDrawing[]> {
  const revisionAtStart = revisionOf(key);
  const res = await novaFetch(`${API_URL}/chart-drawings/${encodeURIComponent(key)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as { drawings?: SerializedDrawing[] };
  const next = Array.isArray(body.drawings) ? body.drawings : [];
  // The operator may have drawn something while this GET was in flight (very
  // likely when the API is slow). Their edit wins -- a stale server list must
  // never erase a line that is already on screen.
  if (revisionOf(key) !== revisionAtStart) return getDrawings(key);
  setLocal(key, next);
  return next;
}

/** Deduped GET. Resolves to the cached list on failure so a pane still paints. */
export function ensureDrawings(symbol: string): Promise<SerializedDrawing[]> {
  const key = drawingsKey(symbol);
  if (!key) return Promise.resolve([]);
  const existing = inflight.get(key);
  if (existing) return existing;

  const promise = fetchDrawings(key)
    .catch(() => getDrawings(key))
    .finally(() => {
      if (inflight.get(key) === promise) inflight.delete(key);
    });
  inflight.set(key, promise);
  return promise;
}

/** Force a refetch even if a cached list exists (focus regain, cross-window ping). */
export function refreshDrawings(symbol: string): Promise<SerializedDrawing[]> {
  const key = drawingsKey(symbol);
  if (inflight.has(key)) return inflight.get(key)!;
  return ensureDrawings(key);
}

function scheduleSave(key: string): void {
  const pending = saveTimers.get(key);
  if (pending) clearTimeout(pending);
  saveTimers.set(
    key,
    setTimeout(() => {
      saveTimers.delete(key);
      void flushSave(key);
    }, CHART_DRAWINGS_SAVE_DEBOUNCE_MS),
  );
}

async function flushSave(key: string): Promise<void> {
  const payload = getDrawings(key);
  try {
    const res = await novaFetch(`${API_URL}/chart-drawings/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ drawings: payload }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    announce(key);
  } catch (err) {
    // Loud, not silent: an unsaved level is a level the operator will lose.
    console.error('chart drawings: failed to persist', key, err);
  }
}

/** Add or replace one drawing (anchors already collapsed to canonical epochs). */
export function upsertDrawing(symbol: string, drawing: SerializedDrawing): void {
  const key = drawingsKey(symbol);
  if (!key) return;
  const current = getDrawings(key);
  const index = current.findIndex((d) => d.id === drawing.id);
  if (index === -1 && current.length >= CHART_DRAWINGS_MAX_PER_SYMBOL) {
    console.warn(
      `chart drawings: ${key} is at the ${CHART_DRAWINGS_MAX_PER_SYMBOL} cap -- not stored`,
    );
    return;
  }
  const next = index === -1
    ? [...current, drawing]
    : current.map((d, i) => (i === index ? drawing : d));
  setLocal(key, next);
  scheduleSave(key);
}

export function removeDrawing(symbol: string, id: string): void {
  const key = drawingsKey(symbol);
  const current = getDrawings(key);
  const next = current.filter((d) => d.id !== id);
  if (next.length === current.length) return;
  setLocal(key, next);
  scheduleSave(key);
}

export function clearDrawings(symbol: string): void {
  const key = drawingsKey(symbol);
  if (!key) return;
  setLocal(key, []);
  const pending = saveTimers.get(key);
  if (pending) {
    clearTimeout(pending);
    saveTimers.delete(key);
  }
  void (async () => {
    try {
      const res = await novaFetch(`${API_URL}/chart-drawings/${encodeURIComponent(key)}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      announce(key);
    } catch (err) {
      console.error('chart drawings: failed to clear', key, err);
    }
  })();
}

export function clearDrawingsStoreForTests(): void {
  for (const timer of saveTimers.values()) clearTimeout(timer);
  saveTimers.clear();
  drawings.clear();
  listeners.clear();
  inflight.clear();
  revisions.clear();
}
