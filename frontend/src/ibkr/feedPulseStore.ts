/**
 * One shared read of `/api/ibkr/feed` per window (#672), once a second while
 * something on screen reads it and the window is visible. Subscribers re-render
 * only when the badge changes (it counts up once a second during a gap). A failed
 * read shows no badge: the header's API state already says when the API is down,
 * and the sample desk's network gate refuses the read.
 */
import { useSyncExternalStore } from 'react';
import { API_BASE_URL, FEED_PULSE_POLL_MS } from '../constants';
import { feedGapBadge, parseFeedPulse, type FeedGapBadge } from './feedPulse';

let badge: FeedGapBadge | null = null;
let timer: number | null = null;
let inFlight = false;
const listeners = new Set<() => void>();

function same(a: FeedGapBadge | null, b: FeedGapBadge | null): boolean {
  return a === b || (a != null && b != null && a.label === b.label && a.title === b.title && a.tone === b.tone);
}

function set(next: FeedGapBadge | null): void {
  if (same(next, badge)) return;
  badge = next;
  listeners.forEach(l => l());
}

async function read(): Promise<void> {
  if (inFlight || (typeof document !== 'undefined' && document.hidden)) return;
  inFlight = true;
  try {
    const res = await fetch(`${API_BASE_URL}/api/ibkr/feed`, { cache: 'no-store' });
    if (!res.ok) {
      set(null);
      return;
    }
    set(feedGapBadge(parseFeedPulse(await res.json()), Date.now() / 1000));
  } catch (err) {
    console.debug('[Nova] feed pulse: /api/ibkr/feed did not answer', err);
    set(null);
  } finally {
    inFlight = false;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer == null) {
    void read();
    timer = window.setInterval(() => void read(), FEED_PULSE_POLL_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer != null) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}

/** NO DATA / DATA GAP for the header chip and Time & Sales, or null while data arrives. */
export function useFeedGapBadge(): FeedGapBadge | null {
  return useSyncExternalStore(subscribe, () => badge, () => null);
}

export function resetFeedPulseForTests(): void {
  badge = null;
  inFlight = false;
  if (timer != null) window.clearInterval(timer);
  timer = null;
  listeners.clear();
}
