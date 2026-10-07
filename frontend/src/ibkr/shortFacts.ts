/**
 * A symbol's short facts for every reader in the window (ADR 048, #778 step 3): SSR, the halt cool-off and the
 * borrow, from the short check asked for one share and no price -- so it never waits on IBKR's what-if.
 *
 * Level 2's chips and the ticket's Short read it: one request per symbol every ``SHORT_CHECK_CHIP_POLL_MS``
 * however many read it, and none once the last reader goes. The sample desk asks nothing ("not available").
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import {
  readShortCheck,
  SHORT_CHECK_CHIP_POLL_MS,
  SHORT_CHECK_IDLE,
  SHORT_CHECK_UNAVAILABLE_STATE,
  shortCheckUrl,
  type ShortCheckState,
} from './shortCheck';

interface Entry {
  state: ShortCheckState;
  readers: number;
  timer: number | null;
  controller: AbortController | null;
  listeners: Set<() => void>;
}

const entries = new Map<string, Entry>();

function entryFor(key: string): Entry {
  let entry = entries.get(key);
  if (!entry) {
    entry = { state: SHORT_CHECK_IDLE, readers: 0, timer: null, controller: null, listeners: new Set() };
    entries.set(key, entry);
  }
  return entry;
}

function publish(entry: Entry, next: ShortCheckState): void {
  entry.state = next;
  for (const listener of [...entry.listeners]) listener();
}

async function read(key: string, entry: Entry): Promise<void> {
  entry.controller?.abort();
  const controller = new AbortController();
  entry.controller = controller;
  try {
    const next = await readShortCheck(shortCheckUrl(key, { qty: 1 }), controller.signal);
    if (entries.get(key) !== entry || entry.readers === 0) return;
    // A failed read keeps the last facts with the error beside them, never a blank that reads as "none".
    publish(entry, next.error && entry.state.check ? { ...entry.state, error: next.error } : next);
  } catch {
    // maintainer: allow-swallow an aborted read: the next read, or the last reader leaving, owns the state
  }
}

/** Start reading ``key`` for one more reader; the returned function stops it. */
function acquire(key: string): () => void {
  const entry = entryFor(key);
  entry.readers += 1;
  if (entry.readers === 1) {
    void read(key, entry);
    entry.timer = window.setInterval(() => void read(key, entry), SHORT_CHECK_CHIP_POLL_MS);
  }
  return () => {
    entry.readers -= 1;
    if (entry.readers > 0) return;
    if (entry.timer != null) window.clearInterval(entry.timer);
    entry.timer = null;
    entry.controller?.abort();
    // Facts are never kept past their last reader: a reader that comes back asks again.
    entry.state = SHORT_CHECK_IDLE;
    if (entry.listeners.size === 0) entries.delete(key);
  };
}

function subscribe(key: string, listener: () => void): () => void {
  const entry = entryFor(key);
  entry.listeners.add(listener);
  return () => {
    entry.listeners.delete(listener);
    if (entry.readers === 0 && entry.listeners.size === 0 && entries.get(key) === entry) entries.delete(key);
  };
}

/** ``symbol``'s short facts while ``enabled`` (false reads nothing and answers idle). */
export function useShortFacts(symbol: string, enabled: boolean): ShortCheckState {
  const sample = useSampleDataOptional();
  const key = symbol.trim().toUpperCase();
  const on = enabled && Boolean(key) && !sample;
  useEffect(() => (on ? acquire(key) : undefined), [key, on]);
  const sub = useCallback((listener: () => void) => (on ? subscribe(key, listener) : () => {}), [key, on]);
  const snap = useCallback(() => (on ? entries.get(key)?.state ?? SHORT_CHECK_IDLE : SHORT_CHECK_IDLE), [key, on]);
  const state = useSyncExternalStore(sub, snap);
  if (enabled && sample) return SHORT_CHECK_UNAVAILABLE_STATE;
  return state;
}

/** Test seam: forget every reader and fact. */
export function resetShortFactsForTests(): void {
  for (const entry of entries.values()) {
    if (entry.timer != null) window.clearInterval(entry.timer);
    entry.controller?.abort();
  }
  entries.clear();
}
