/**
 * The Catalyst column's reads (ADR 028 amendment 2026-10-12): every cell on screen shares one
 * `GET /api/why?symbols=...&board=...` per board, so a 50-row board is one request, not fifty. A cell on a board
 * asks for its row on that board (`board`), read at the price the row shows; a cell on no board (HOD Momo, the
 * Contenders, the focus rail) asks with no board and gets the Trader card's read.
 *
 * Reads repeat every `WHY_MOVING_POLL_MS` while a cell shows them. On a Sim replay they follow the playhead the
 * way the Trader card does (`useWhyMoving`): a rewind, or a move between a replay and the live desk, drops every
 * read on screen and reads again -- an answer in flight across the rewind is thrown away -- and playing forward
 * reads again once the playhead is `WHY_MOVING_REPLAY_REFRESH_SEC` past the last read. An API from before the
 * batch route (404) makes the column fall back to the news mark (`unavailable`).
 *
 * Owner: this module (module state: the reads by `board|symbol`, the cells listening, the playhead).
 */
import {
  API_BASE_URL,
  CATALYST_BATCH_DEBOUNCE_MS,
  CATALYST_BATCH_MAX,
  CATALYST_FAILED_PREFIX,
  WHY_MOVING_PATH,
  WHY_MOVING_POLL_MS,
  WHY_MOVING_REPLAY_REFRESH_SEC,
} from '../constants';
import type { WhyMovingRead } from '../types/whyMoving';
import { normalizeWhyMoving } from './useWhyMoving';

export interface CatalystReadState {
  read: WhyMovingRead | null;
  loading: boolean;
  /** The last read's failure; the last good read stays. */
  error: string | null;
}

type Listener = () => void;

const LOADING: CatalystReadState = Object.freeze({ read: null, loading: true, error: null });

export function catalystKey(symbol: string, board: string | null): string {
  return `${board ?? ''}|${symbol.trim().toUpperCase()}`;
}

function splitKey(key: string): [string, string] {
  const at = key.indexOf('|');
  return [key.slice(0, at), key.slice(at + 1)];
}

export class WhyBatchStore {
  private entries = new Map<string, CatalystReadState>();
  private fetchedAt = new Map<string, number>();
  private listeners = new Map<string, Set<Listener>>();
  private pending = new Set<string>();
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private generation = 0;
  private playhead: number | null = null;
  private askedAt: number | null = null;
  private unavailable = false;
  private unavailableListeners = new Set<Listener>();

  private readonly fetcher: (url: string) => Promise<Response>;

  constructor(fetcher: (url: string) => Promise<Response> = (url) => fetch(url)) {
    this.fetcher = fetcher;
  }

  subscribe = (key: string, listener: Listener): (() => void) => {
    let set = this.listeners.get(key);
    if (!set) {
      set = new Set();
      this.listeners.set(key, set);
    }
    set.add(listener);
    const age = Date.now() - (this.fetchedAt.get(key) ?? 0);
    if (!this.entries.has(key)) this.entries.set(key, LOADING);
    if (age >= WHY_MOVING_POLL_MS) this.request(key);
    this.ensurePoll();
    return () => {
      set?.delete(listener);
      if (set?.size === 0) this.listeners.delete(key);
      if (this.listeners.size === 0) this.stopPoll();
    };
  };

  getSnapshot = (key: string): CatalystReadState => this.entries.get(key) ?? LOADING;

  subscribeUnavailable = (listener: Listener): (() => void) => {
    this.unavailableListeners.add(listener);
    return () => { this.unavailableListeners.delete(listener); };
  };

  isUnavailable = (): boolean => this.unavailable;

  /** The Sim replay's playhead (epoch seconds), or null off a replay. */
  setPlayhead(sec: number | null): void {
    const prev = this.playhead;
    this.playhead = sec;
    const switched = (prev == null) !== (sec == null);
    if (switched || (sec != null && prev != null && sec < prev)) {
      this.generation += 1;
      for (const key of this.entries.keys()) {
        this.entries.set(key, LOADING);
        this.fetchedAt.delete(key);
        this.notify(key);
      }
      this.requestListened();
    } else if (sec != null && this.askedAt != null && sec - this.askedAt >= WHY_MOVING_REPLAY_REFRESH_SEC) {
      this.requestListened();
    }
  }

  /** Tests only. */
  reset(): void {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.stopPoll();
    this.entries.clear();
    this.fetchedAt.clear();
    this.listeners.clear();
    this.pending.clear();
    this.flushTimer = null;
    this.generation = 0;
    this.playhead = null;
    this.askedAt = null;
    this.unavailable = false;
  }

  private request(key: string): void {
    this.pending.add(key);
    if (this.flushTimer == null) {
      this.flushTimer = setTimeout(() => {
        this.flushTimer = null;
        void this.flush();
      }, CATALYST_BATCH_DEBOUNCE_MS);
    }
  }

  private requestListened(): void {
    for (const key of this.listeners.keys()) this.request(key);
  }

  private ensurePoll(): void {
    if (this.pollTimer == null) this.pollTimer = setInterval(() => this.requestListened(), WHY_MOVING_POLL_MS);
  }

  private stopPoll(): void {
    if (this.pollTimer != null) clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  private notify(key: string): void {
    for (const l of this.listeners.get(key) ?? []) l();
  }

  private async flush(): Promise<void> {
    if (this.unavailable) return;
    const byBoard = new Map<string, string[]>();
    for (const key of this.pending) {
      const [board, symbol] = splitKey(key);
      byBoard.set(board, [...(byBoard.get(board) ?? []), symbol]);
    }
    this.pending.clear();
    this.askedAt = this.playhead;
    const mine = this.generation;
    const jobs: Promise<void>[] = [];
    for (const [board, symbols] of byBoard) {
      for (let i = 0; i < symbols.length; i += CATALYST_BATCH_MAX) {
        jobs.push(this.fetchChunk(board || null, symbols.slice(i, i + CATALYST_BATCH_MAX), mine));
      }
    }
    await Promise.all(jobs);
  }

  private async fetchChunk(board: string | null, symbols: string[], mine: number): Promise<void> {
    const query = `symbols=${encodeURIComponent(symbols.join(','))}${board ? `&board=${encodeURIComponent(board)}` : ''}`;
    let body: Record<string, unknown> | null = null;
    let failure: string | null = null;
    try {
      const res = await this.fetcher(`${API_BASE_URL}${WHY_MOVING_PATH}?${query}`);
      if (res.status === 404) {
        this.unavailable = true;  // an API from before the batch route: the column shows the news mark
        for (const l of this.unavailableListeners) l();
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      body = raw && typeof raw === 'object' ? raw as Record<string, unknown> : null;
      if (!body || typeof body.reads !== 'object' || body.reads == null) throw new Error('not a batch read');
    } catch (e) {
      failure = `${CATALYST_FAILED_PREFIX}: ${e instanceof Error ? e.message : String(e)}`;
    }
    if (mine !== this.generation) return;  // a rewind came while this was in flight
    const reads = (body?.reads ?? {}) as Record<string, unknown>;
    const errors = (body?.errors ?? {}) as Record<string, unknown>;
    for (const symbol of symbols) {
      const key = catalystKey(symbol, board);
      const prev = this.entries.get(key) ?? LOADING;
      const read = failure ? null : normalizeWhyMoving(reads[symbol]);
      const error = failure
        ?? (typeof errors[symbol] === 'string' ? `${CATALYST_FAILED_PREFIX}: ${errors[symbol]}` : null)
        ?? (read ? null : `${CATALYST_FAILED_PREFIX}: no read for ${symbol}`);
      this.entries.set(key, { read: read ?? prev.read, loading: false, error });
      if (read) this.fetchedAt.set(key, Date.now());
      this.notify(key);
    }
  }
}

export const whyBatchStore = new WhyBatchStore();
