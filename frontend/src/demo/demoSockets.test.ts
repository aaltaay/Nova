/**
 * @vitest-environment jsdom
 *
 * The demo's sockets (ADR 043): they open in the page, deliver their path's frames, tick with the
 * sample market, and stop when closed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetDemoState } from './demoApi';
import { DemoSocket } from './demoSockets';

function collect(url: string) {
  const frames: { type: string; [k: string]: unknown }[] = [];
  const ws = new DemoSocket(url);
  ws.onmessage = (ev) => frames.push(JSON.parse(String(ev.data)));
  return { ws, frames };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  resetDemoState();
});

describe('DemoSocket', () => {
  it('opens in the page and sends the HOD Momo feed', () => {
    const { ws, frames } = collect('ws://nova-demo.invalid/ws/hod-momo');
    const opened = vi.fn();
    ws.addEventListener('open', opened);
    expect(ws.readyState).toBe(DemoSocket.CONNECTING);
    vi.advanceTimersByTime(30);
    expect(opened).toHaveBeenCalledOnce();
    expect(ws.readyState).toBe(DemoSocket.OPEN);
    expect(frames[0]).toMatchObject({ type: 'initial', total: 47 });
    vi.advanceTimersByTime(50_000);
    expect(frames.at(-1)?.type).toBe('alert');
    ws.close();
  });

  it("ticks a symbol's tape and stops when closed", () => {
    const { ws, frames } = collect('ws://nova-demo.invalid/ws/ibkr/tape/SMPL');
    vi.advanceTimersByTime(30);
    expect(frames[0]).toMatchObject({ type: 'subscribed', symbol: 'SMPL' });
    const seeded = frames.length;
    expect(seeded).toBeGreaterThan(50);
    vi.advanceTimersByTime(10_000);
    const ticked = frames.length;
    expect(ticked).toBeGreaterThan(seeded);
    const last = frames.at(-1) as { price: number; side: string };
    expect(last.price).toBeGreaterThanOrEqual(4.3);
    expect(last.price).toBeLessThanOrEqual(4.35);
    ws.close();
    vi.advanceTimersByTime(10_000);
    expect(frames.length).toBe(ticked);
    expect(ws.readyState).toBe(DemoSocket.CLOSED);
  });

  it('stays open and silent on a path it does not know', () => {
    const { ws, frames } = collect('ws://nova-demo.invalid/ws/scanner');
    vi.advanceTimersByTime(5_000);
    expect(ws.readyState).toBe(DemoSocket.OPEN);
    expect(frames).toEqual([]);
    ws.close();
  });
});
