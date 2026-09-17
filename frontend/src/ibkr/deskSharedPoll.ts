/**
 * Cross-window single-owner poll share (Electron + Vite + popouts).
 * Leader heartbeats in localStorage. Followers apply BroadcastChannel /
 * storage snapshots. If the leader heartbeat is older than staleMs,
 * this tab claims. Missing storage => this tab polls (tests / private mode).
 */
import {
  DESK_POLL_CHANNEL_PREFIX,
  DESK_POLL_LEADER_KEY_PREFIX,
  DESK_POLL_SNAP_KEY_PREFIX,
  DESK_POLL_TAB_SESSION_KEY,
} from '../constants';

export type DeskPollEnvelope<T> = { ts: number; payload: T };

type LeaderRow = { owner: string; ts: number };

const channels = new Map<string, BroadcastChannel>();

function nowMs(now?: number): number {
  return now ?? Date.now();
}

export function deskPollOwnerId(): string {
  if (typeof sessionStorage === 'undefined') {
    return 'tab-memory';
  }
  try {
    let id = sessionStorage.getItem(DESK_POLL_TAB_SESSION_KEY);
    if (!id) {
      id = `tab-${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem(DESK_POLL_TAB_SESSION_KEY, id);
    }
    return id;
  } catch {
    return 'tab-memory';
  }
}

function leaderKey(name: string): string {
  return `${DESK_POLL_LEADER_KEY_PREFIX}${name}`;
}

function snapKey(name: string): string {
  return `${DESK_POLL_SNAP_KEY_PREFIX}${name}`;
}

function channelName(name: string): string {
  return `${DESK_POLL_CHANNEL_PREFIX}${name}`;
}

function readLeader(name: string): LeaderRow | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(leaderKey(name));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LeaderRow;
    if (!parsed?.owner || typeof parsed.ts !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeLeader(name: string, owner: string, ts: number): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(leaderKey(name), JSON.stringify({ owner, ts }));
  } catch {
    /* private mode / quota */
  }
}

export function claimDeskPollLeader(
  name: string,
  staleMs: number,
  now?: number,
): boolean {
  const ts = nowMs(now);
  const owner = deskPollOwnerId();
  const current = readLeader(name);
  if (current && current.owner !== owner && ts - current.ts < staleMs) {
    return false;
  }
  writeLeader(name, owner, ts);
  return true;
}

export function heartbeatDeskPollLeader(name: string, now?: number): void {
  writeLeader(name, deskPollOwnerId(), nowMs(now));
}

export function publishDeskPollSnap<T>(name: string, payload: T, now?: number): void {
  const env: DeskPollEnvelope<T> = { ts: nowMs(now), payload };
  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(snapKey(name), JSON.stringify(env));
    } catch {
      /* private mode / quota */
    }
  }
  const ch = getChannel(name);
  try {
    ch?.postMessage(env);
  } catch {
    /* closed channel */
  }
}

export function readDeskPollSnap<T>(name: string): DeskPollEnvelope<T> | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(snapKey(name));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DeskPollEnvelope<T>;
    if (!parsed || typeof parsed.ts !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

function getChannel(name: string): BroadcastChannel | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  const existing = channels.get(name);
  if (existing) return existing;
  try {
    const ch = new BroadcastChannel(channelName(name));
    channels.set(name, ch);
    return ch;
  } catch {
    return null;
  }
}

export function subscribeDeskPollSnap<T>(
  name: string,
  onSnap: (env: DeskPollEnvelope<T>) => void,
): () => void {
  const existing = readDeskPollSnap<T>(name);
  if (existing) onSnap(existing);

  const ch = getChannel(name);
  const onMsg = (ev: MessageEvent<DeskPollEnvelope<T>>) => {
    if (ev.data && typeof ev.data.ts === 'number') onSnap(ev.data);
  };
  ch?.addEventListener('message', onMsg);

  const onStorage = (ev: StorageEvent) => {
    if (ev.key !== snapKey(name) || !ev.newValue) return;
    try {
      const parsed = JSON.parse(ev.newValue) as DeskPollEnvelope<T>;
      if (parsed && typeof parsed.ts === 'number') onSnap(parsed);
    } catch {
      /* ignore */
    }
  };
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', onStorage);
  }

  return () => {
    ch?.removeEventListener('message', onMsg);
    if (typeof window !== 'undefined') {
      window.removeEventListener('storage', onStorage);
    }
  };
}

export function _resetDeskPollShareForTests(): void {
  channels.forEach((ch) => {
    try {
      ch.close();
    } catch {
      /* ignore */
    }
  });
  channels.clear();
  if (typeof localStorage !== 'undefined') {
    const doomed: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (
        key
        && (key.startsWith(DESK_POLL_LEADER_KEY_PREFIX)
          || key.startsWith(DESK_POLL_SNAP_KEY_PREFIX))
      ) {
        doomed.push(key);
      }
    }
    doomed.forEach((key) => localStorage.removeItem(key));
  }
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem(DESK_POLL_TAB_SESSION_KEY);
  }
}
