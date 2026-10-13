/**
 * Whether this desk has a followed traders feed: one probe per window of `GET /api/followed-traders/config`,
 * a route the backend registers only when NOVA_FOLLOW_FEED_URL is set. A 404 (the default, every public
 * install) is off and is never asked again; an answer means the same for the life of the window. Only a
 * backend that did not answer at all (still starting) is asked again. The sample desk asks nothing.
 */
import { useSyncExternalStore } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { FOLLOWED_CONFIG_PATH, FOLLOWED_PROBE_RETRY_MS } from './constants';

export type FollowedGate = 'unknown' | 'on' | 'off';

const MAX_RETRIES = 30;
let gate: FollowedGate = 'unknown';
let started = false;
let retries = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function set(next: FollowedGate): void {
  if (gate === next) return;
  gate = next;
  for (const l of listeners) l();
}

async function probe(): Promise<void> {
  timer = null;
  try {
    const res = await novaFetch(`${API_BASE_URL}${FOLLOWED_CONFIG_PATH}`);
    if (res.status >= 500) throw new Error(`HTTP ${res.status}`);
    if (!res.ok) {
      set('off');
      return;
    }
    const body = (await res.json()) as { enabled?: unknown } | null;
    set(body?.enabled === true ? 'on' : 'off');
  } catch {
    // No answer: the backend may still be starting. Ask again, a bounded number of times.
    retries += 1;
    if (retries < MAX_RETRIES) timer = setTimeout(() => void probe(), FOLLOWED_PROBE_RETRY_MS);
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (!started) {
    started = true;
    void probe();
  }
  return () => {
    listeners.delete(listener);
  };
}

const noSubscribe = () => () => {};
const read = () => gate;
const readOff = (): FollowedGate => 'off';

/** True only once the backend said the feed is configured. */
export function useFollowedTradersEnabled(): boolean {
  const sample = useSampleRoute();
  const value = useSyncExternalStore(sample ? noSubscribe : subscribe, sample ? readOff : read, readOff);
  return value === 'on';
}

/** Test helper. */
export function resetFollowedGateForTests(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  gate = 'unknown';
  started = false;
  retries = 0;
  listeners.clear();
}
