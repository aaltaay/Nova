/**
 * Scoped BroadcastChannel for trader extract/dock. Not a product-wide bus.
 */

import { TRADER_DESK_CHANNEL, parseTraderDeskMessage, type TraderDeskMessage } from './protocol';

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

function openChannel(name: string): ChannelLike | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  try {
    return new BroadcastChannel(name);
  } catch {
    return null;
  }
}

export function createTraderDeskBus(channelName = TRADER_DESK_CHANNEL): TraderDeskBus {
  const channel = openChannel(channelName);
  const listeners = new Set<(msg: TraderDeskMessage) => void>();

  const onMessage = (ev: MessageEvent) => {
    const msg = parseTraderDeskMessage(ev.data);
    if (!msg) return;
    listeners.forEach((fn) => fn(msg));
  };

  if (channel) {
    channel.addEventListener('message', onMessage);
  }

  return {
    publish(msg) {
      try {
        channel?.postMessage(msg);
      } catch {
        /* private mode / closed */
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
    },
  };
}
