/**
 * Scoped desk bus for trader extract/dock. Not a product-wide bus.
 *
 * BroadcastChannel works for window.open peers. Electron Pop out uses
 * `new BrowserWindow`, which is a separate browsing-context group, so
 * BC stays silent. localStorage `storage` events still cross those windows.
 */

import {
  TRADER_DESK_CHANNEL,
  TRADER_DESK_STORAGE_KEY,
  encodeDeskStoragePayload,
  parseDeskStoragePayload,
  parseTraderDeskMessage,
  type TraderDeskMessage,
} from './protocol';

export type TraderDeskBus = {
  publish: (msg: TraderDeskMessage) => void;
  subscribe: (fn: (msg: TraderDeskMessage) => void) => () => void;
  close: () => void;
};

type ChannelLike = {
  postMessage: (data: unknown) => void;
  addEventListener: (type: 'message', fn: (ev: MessageEvent) => void) => void;
  removeEventListener: (type: 'message', fn: (ev: MessageEvent) => void) => void;
  close: () => void;
};

const DEDUP_MS = 750;

function openChannel(name: string): ChannelLike | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  try {
    return new BroadcastChannel(name);
  } catch {
    return null;
  }
}

function deskMessageKey(msg: TraderDeskMessage): string {
  return `${msg.type}|${msg.sourceWindowId}|${msg.requestId ?? ''}|${msg.symbol ?? ''}`;
}

export function createTraderDeskBus(channelName = TRADER_DESK_CHANNEL): TraderDeskBus {
  const channel = openChannel(channelName);
  const listeners = new Set<(msg: TraderDeskMessage) => void>();
  const seen = new Map<string, number>();

  const fanout = (msg: TraderDeskMessage) => {
    const key = deskMessageKey(msg);
    const now = Date.now();
    const prev = seen.get(key);
    if (prev != null && now - prev < DEDUP_MS) return;
    seen.set(key, now);
    listeners.forEach((fn) => fn(msg));
  };

  const onMessage = (ev: MessageEvent) => {
    const msg = parseTraderDeskMessage(ev.data);
    if (msg) fanout(msg);
  };

  const onStorage = (ev: StorageEvent) => {
    if (ev.key !== TRADER_DESK_STORAGE_KEY) return;
    const msg = parseDeskStoragePayload(ev.newValue);
    if (msg) fanout(msg);
  };

  if (channel) {
    channel.addEventListener('message', onMessage);
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', onStorage);
  }

  return {
    publish(msg) {
      try {
        channel?.postMessage(msg);
      } catch {
        /* private mode / closed */
      }
      try {
        localStorage.setItem(TRADER_DESK_STORAGE_KEY, encodeDeskStoragePayload(msg));
      } catch {
        /* private mode / quota */
      }
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
    close() {
      listeners.clear();
      try {
        channel?.removeEventListener('message', onMessage);
        channel?.close();
      } catch {
        /* already closed */
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', onStorage);
      }
    },
  };
}
