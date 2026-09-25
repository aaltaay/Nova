/**
 * Which revision the local API process runs -- `/api/health` `release_tag` -- for the window
 * title (operator ask 2026-09-24: "something in the software title that shows us what backend
 * v### we are using"). A backend left running across an update keeps its old code until it
 * restarts; the title says which one answers. One shared poll per window while something reads
 * it, every BACKEND_TAG_POLL_MS and at once when the window regains focus. A failed read keeps
 * the last answer (the header's API status says when the API is down); the sample desk's
 * network gate refuses the read, so its title never names a backend. A backend older than the
 * field (before v1007) still names its revision in its checklist (`/api/diagnostics`
 * `process.release_tag`): that is read once per backend process, never on every poll.
 * The same read keeps `checkout_tag`, the backend's checkout revision on disk now: a restart
 * loads that, so it says whether a restart would help (operator report 2026-09-25).
 */
import { useSyncExternalStore } from 'react';
import { API_BASE_URL, BACKEND_TAG_POLL_MS } from '../constants';

let tag: string | null = null;
let checkoutTag: string | null = null;
let timer: number | null = null;
let inFlight: Promise<void> | null = null;
/** The backend process whose checklist was already asked (a backend older than the field). */
let checkedInstance: string | null = null;
const listeners = new Set<() => void>();

function set(next: string | null, nextCheckout: string | null): void {
  if (next === tag && nextCheckout === checkoutTag) return;
  tag = next;
  checkoutTag = nextCheckout;
  listeners.forEach(l => l());
}

function tagOf(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/**
 * An older backend's revision from its checklist, once per process. Unknown (null) when the
 * checklist does not say or does not answer -- never the last process's revision -- and asked
 * again on the next poll until it answers.
 */
async function readFromChecklist(instanceId: string): Promise<void> {
  if (instanceId === checkedInstance) return;
  try {
    const res = await fetch(`${API_BASE_URL}/api/diagnostics`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`diagnostics HTTP ${res.status}`);
    const body = (await res.json()) as { process?: { release_tag?: unknown } };
    checkedInstance = instanceId;
    // A backend this old reports no checkout revision either.
    set(tagOf(body?.process?.release_tag), null);
  } catch (err) {
    console.debug('[Nova] backend revision: the checklist did not answer', err);
    set(null, null);
  }
}

async function read(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`, { cache: 'no-store' });
    if (!res.ok) return;
    const body = (await res.json()) as { release_tag?: unknown; checkout_tag?: unknown; instance_id?: unknown };
    const direct = tagOf(body?.release_tag);
    const instanceId = tagOf(body?.instance_id);
    if (direct || !instanceId) {
      set(direct, tagOf(body?.checkout_tag));
      return;
    }
    await readFromChecklist(instanceId);
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

function checkoutSnapshot(): string | null {
  return checkoutTag;
}

/** The backend's revision as last read (`v1006`), or null while unknown. */
export function currentBackendReleaseTag(): string | null {
  return tag;
}

/** The backend's checkout revision on disk as last read (`v1006`), or null while unknown. */
export function currentBackendCheckoutTag(): string | null {
  return checkoutTag;
}

/** The backend's revision (`v1006`), or null while unknown. */
export function useBackendReleaseTag(): string | null {
  return useSyncExternalStore(subscribe, snapshot, () => null);
}

/** The backend's checkout revision on disk now (`v1006`), or null while unknown. */
export function useBackendCheckoutTag(): string | null {
  return useSyncExternalStore(subscribe, checkoutSnapshot, () => null);
}

/** Test helper. */
export function resetBackendReleaseTagForTests(): void {
  tag = null;
  checkoutTag = null;
  inFlight = null;
  checkedInstance = null;
}
