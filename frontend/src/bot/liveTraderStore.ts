/**
 * The Live Trader bot's two polls (ADR 055), shared by every component of a window: the cards
 * (`GET /api/bot/live-traders`, while the TraderTV LIVE page shows them) and the asks with what the bot holds
 * (`GET /api/bot/live-traders/asks`, every desk window, for the toasts and the Bot switch's question). A poll runs
 * only while something reads it; a write's answer replaces the cards at once. In memory, per window.
 */
import { useCallback, useSyncExternalStore } from 'react';
import { LT_ASKS_POLL_MS, LT_POLL_MS } from '../constantGroups/live_trader';
import { fetchLiveTraderAsks, fetchLiveTraders } from './liveTraderApi';
import type { LiveTraderAsksView, LiveTradersView } from './liveTraderTypes';

export interface PollSnap<T> {
  view: T | null;
  error: string | null;
}

class Poll<T> {
  private snap: PollSnap<T> = { view: null, error: null };
  private readonly listeners = new Set<() => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private inFlight = false;
  private readonly fetcher: () => Promise<T>;
  private readonly ms: number;

  constructor(fetcher: () => Promise<T>, ms: number) {
    this.fetcher = fetcher;
    this.ms = ms;
  }

  readonly get = (): PollSnap<T> => this.snap;

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    if (this.listeners.size === 1) {
      void this.refresh();
      this.timer = setInterval(() => void this.refresh(), this.ms);
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0 && this.timer !== null) {
        clearInterval(this.timer);
        this.timer = null;
      }
    };
  };

  readonly refresh = async (): Promise<T | null> => {
    if (this.inFlight) return this.snap.view;
    this.inFlight = true;
    try {
      const view = await this.fetcher();
      this.set({ view, error: null });
      return view;
    } catch (err) {
      this.set({ view: this.snap.view, error: err instanceof Error ? err.message : String(err) });
      return null;
    } finally {
      this.inFlight = false;
    }
  };

  set(next: PollSnap<T>): void {
    this.snap = next;
    for (const l of this.listeners) l();
  }

  reset(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.inFlight = false;
    this.snap = { view: null, error: null };
    this.listeners.clear();
  }
}

export const cardsPoll = new Poll<LiveTradersView>(fetchLiveTraders, LT_POLL_MS);
export const asksPoll = new Poll<LiveTraderAsksView>(fetchLiveTraderAsks, LT_ASKS_POLL_MS);

const idle = (): (() => void) => () => undefined;

export function useLiveTraders(active = true) {
  const snap = useSyncExternalStore(active ? cardsPoll.subscribe : idle, cardsPoll.get, cardsPoll.get);
  const apply = useCallback((view: LiveTradersView) => cardsPoll.set({ view, error: null }), []);
  const fail = useCallback((error: string) => cardsPoll.set({ view: cardsPoll.get().view, error }), []);
  return { ...snap, refresh: cardsPoll.refresh, apply, fail };
}

export function useLiveTraderAsks(active = true) {
  const snap = useSyncExternalStore(active ? asksPoll.subscribe : idle, asksPoll.get, asksPoll.get);
  return { ...snap, refresh: asksPoll.refresh };
}

export function _resetLiveTraderPollsForTests(): void {
  cardsPoll.reset();
  asksPoll.reset();
}
