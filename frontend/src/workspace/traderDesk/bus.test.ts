/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTraderDeskBus } from './bus';
import {
  TRADER_DESK_STORAGE_KEY,
  encodeDeskStoragePayload,
  traderDeskMessage,
} from './protocol';

describe('trader desk bus storage fallback', () => {
  beforeEach(() => {
    localStorage.removeItem(TRADER_DESK_STORAGE_KEY);
  });

  afterEach(() => {
    localStorage.removeItem(TRADER_DESK_STORAGE_KEY);
    vi.unstubAllGlobals();
  });

  it('delivers a dock-request through a storage event when BroadcastChannel is dark', () => {
    vi.stubGlobal('BroadcastChannel', undefined);
    const bus = createTraderDeskBus();
    const received: string[] = [];
    const stop = bus.subscribe((msg) => {
      if (msg.type === 'dock-request' && msg.symbol) received.push(msg.symbol);
    });
    const msg = traderDeskMessage('dock-request', {
      symbol: 'F',
      sourceWindowId: 'float-1',
      requestId: 'req-1',
    });
    window.dispatchEvent(new StorageEvent('storage', {
      key: TRADER_DESK_STORAGE_KEY,
      newValue: encodeDeskStoragePayload(msg, 'seq-dark'),
    }));
    expect(received).toEqual(['F']);
    stop();
    bus.close();
  });

  it('writes a storage signal on publish so a peer Electron window can hear it', () => {
    vi.stubGlobal('BroadcastChannel', undefined);
    const bus = createTraderDeskBus();
    bus.publish(traderDeskMessage('dock-request', {
      symbol: 'F',
      sourceWindowId: 'float-1',
      requestId: 'req-2',
    }));
    const raw = localStorage.getItem(TRADER_DESK_STORAGE_KEY);
    expect(raw).toBeTruthy();
    expect(raw).toMatch(/"type":"dock-request"/);
    expect(raw).toMatch(/"symbol":"F"/);
    bus.close();
  });
});
