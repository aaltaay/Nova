import { afterEach, describe, expect, it } from 'vitest';
import { PERF_MAX_RENDER_KEYS, PERF_MAX_SOCKET_KEYS } from '../constantGroups/perf';
import {
  countRender,
  countSocketMessage,
  frameBytes,
  resetPerfCountersForTests,
  takeCounters,
} from './perfCounters';

afterEach(() => resetPerfCountersForTests());

describe('perf counters', () => {
  it('counts messages, bytes and renders per name', () => {
    countSocketMessage('tape', 10);
    countSocketMessage('tape', 5);
    countSocketMessage('depth', 100);
    countRender('DepthLadder');
    countRender('DepthLadder');
    countRender('GlobalAppBar');
    expect(takeCounters()).toEqual({
      sockets: { tape: { messages: 2, bytes: 15 }, depth: { messages: 1, bytes: 100 } },
      renders: { DepthLadder: 2, GlobalAppBar: 1 },
    });
  });

  it('starts from zero after a take, and leaves a quiet socket out', () => {
    countSocketMessage('tape', 10);
    countRender('DepthLadder');
    takeCounters();
    expect(takeCounters()).toEqual({ sockets: {}, renders: {} });
    countSocketMessage('tape', 3);
    expect(takeCounters().sockets).toEqual({ tape: { messages: 1, bytes: 3 } });
  });

  it('ignores new names past the key caps but keeps counting known ones', () => {
    for (let i = 0; i < PERF_MAX_SOCKET_KEYS + 5; i += 1) countSocketMessage(`s${i}`, 1);
    for (let i = 0; i < PERF_MAX_RENDER_KEYS + 5; i += 1) countRender(`R${i}`);
    countSocketMessage('s0', 1);
    countRender('R0');
    const out = takeCounters();
    expect(Object.keys(out.sockets)).toHaveLength(PERF_MAX_SOCKET_KEYS);
    expect(Object.keys(out.renders)).toHaveLength(PERF_MAX_RENDER_KEYS);
    expect(out.sockets.s0).toEqual({ messages: 2, bytes: 2 });
    expect(out.renders.R0).toBe(2);
    expect(out.sockets[`s${PERF_MAX_SOCKET_KEYS}`]).toBeUndefined();
  });

  it('sizes a string, an ArrayBuffer and a Blob frame', () => {
    expect(frameBytes('{"a":1}')).toBe(7);
    expect(frameBytes(new ArrayBuffer(12))).toBe(12);
    expect(frameBytes(new Blob(['abcd']))).toBe(4);
    expect(frameBytes(null)).toBe(0);
  });
});
