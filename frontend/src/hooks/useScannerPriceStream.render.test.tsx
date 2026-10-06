// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useScannerPriceStream } from './useScannerPriceStream';

class Socket {
  static OPEN = 1;
  static latest: Socket;
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor() { Socket.latest = this; }
  frame(frame: unknown) { this.onmessage?.({ data: JSON.stringify(frame) }); }
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-09-24T13:00:00Z'));
  vi.stubGlobal('WebSocket', Socket);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it('delivers validated halt overlays without claiming a fresh price and ignores the history switch', () => {
  const onHaltPatch = vi.fn();
  const onPatch = vi.fn();
  const { result, rerender } = renderHook(({ enabled }) => useScannerPriceStream({ enabled, onPatch, onHaltPatch }),
    { initialProps: { enabled: true } });
  const socket = Socket.latest;
  act(() => socket.frame({ type: 'halt_patch', rows: [{ symbol: 'pfsa', halted: true }, { symbol: 'X', halted: 0 }] }));
  expect(onHaltPatch).toHaveBeenCalledWith([{ symbol: 'PFSA', halted: true }]);
  expect(onPatch).not.toHaveBeenCalled();
  expect(result.current.lastPriceTs).toBe(0);
  expect(result.current.rowQuoteTs).toEqual({});
  expect(result.current.flashSymbols).toEqual({});
  rerender({ enabled: false });
  act(() => socket.frame({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted: false }] }));
  expect(onHaltPatch).toHaveBeenCalledTimes(1);
});
