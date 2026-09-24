/**
 * Which revision the local API process runs -- `/api/health` `release_tag` -- for the window
 * title (operator ask 2026-09-24: "something in the software title that shows us what backend
 * v### we are using"). A backend left running across an update keeps its old code until it
 * restarts; the title says which one answers. One shared poll per window while something reads
 * it, every BACKEND_TAG_POLL_MS and at once when the window regains focus. A failed read keeps
 * the last answer (the header's API status says when the API is down); the sample desk's
 * network gate refuses the read, so its title never names a backend.
 */
import { useSyncExternalStore } from 'react';
import { API_BASE_URL, BACKEND_TAG_POLL_MS } from '../constants';

let tag: string | null = null;
let timer: number | null = null;
let inFlight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function set(next: string | null): void {
  if (next === tag) return;
  tag = next;
  listeners.forEach(l => l());
}

async function read(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`, { cache: 'no-store' });
    if (!res.ok) return;
    const body = (await res.json()) as { release_tag?: unknown };
    const raw = typeof body?.release_tag === 'string' ? body.release_tag.trim() : '';
    set(raw || null);
  } catch (err) {
    // The API is down or restarting: keep the last answer until it is back.
    console.debug('[Nova] backend revision read failed', err);
  }
}

/** Ask the API now (a reload just finished, the window came back); joins a read already running. */
export function refreshBackendReleaseTag(): Promise<void> {
  inFlight ??= read().finally(() => { inFlight = null; });
  return inFlight;
}

const onFocus = () => void refreshBackendReleaseTag();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1 && typeof window !== 'undefined') {
    void refreshBackendReleaseTag();
    timer = window.setInterval(() => void refreshBackendReleaseTag(), BACKEND_TAG_POLL_MS);
    window.addEventListener('focus', onFocus);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && typeof window !== 'undefined') {
      if (timer != null) window.clearInterval(timer);
      timer = null;
      window.removeEventListener('focus', onFocus);
    }
  };
}

function snapshot(): string | null {
  return tag;
}

/** The backend's revision as last read (`v1006`), or null while unknown. */
export function currentBackendReleaseTag(): string | null {
  return tag;
}

/** The backend's revision (`v1006`), or null while unknown. */
export function useBackendReleaseTag(): string | null {
  return useSyncExternalStore(subscribe, snapshot, () => null);
}

/** Test helper. */
export function resetBackendReleaseTagForTests(): void {
  tag = null;
  inFlight = null;
}
