import { describe, expect, it } from 'vitest';
import { p95, startFrameMeter, type FrameMeterEnv } from './frameMeter';

/** A synthetic rAF: frames run only when the test calls `frame(ts)`. */
function fakeEnv(visible = true) {
  let pending: ((ts: number) => void) | null = null;
  let listener: (() => void) | null = null;
  let nextId = 1;
  const state = { visible };
  const env: FrameMeterEnv = {
    requestFrame: (cb) => {
      pending = cb;
      return nextId++;
    },
    cancelFrame: () => {
      pending = null;
    },
    isVisible: () => state.visible,
    onVisibilityChange: (cb) => {
      listener = cb;
      return () => {
        listener = null;
      };
    },
  };
  return {
    env,
    frame(ts: number) {
      const cb = pending;
      pending = null;
      cb?.(ts);
    },
    frames(from: number, intervals: number[]) {
      let ts = from;
      this.frame(ts);
      for (const dt of intervals) {
        ts += dt;
        this.frame(ts);
      }
      return ts;
    },
    setVisible(next: boolean) {
      state.visible = next;
      listener?.();
    },
    hasPending: () => pending !== null,
  };
}

describe('frame meter', () => {
  it('p95 is the nearest-rank 95th percentile', () => {
    const values = Float64Array.from([...Array(19).fill(16), 100]);
    expect(p95(values, 20)).toBe(16);
    expect(p95(Float64Array.from([...Array(18).fill(16), 50, 100]), 20)).toBe(50);
    expect(p95(new Float64Array(4), 0)).toBeNull();
  });

  it('counts intervals, slow ones past 33 ms, and the p95', () => {
    const fake = fakeEnv();
    const meter = startFrameMeter(fake.env);
    fake.frames(1000, [...Array(18).fill(16.7), 40, 120]);
    expect(meter.take()).toEqual({ count: 20, slow: 2, p95_ms: 40 });
    expect(meter.take()).toBeNull();
    meter.stop();
  });

  it('measures nothing while hidden: null for a window hidden the whole interval', () => {
    const fake = fakeEnv(false);
    const meter = startFrameMeter(fake.env);
    expect(fake.hasPending()).toBe(false);
    expect(meter.take()).toBeNull();
    meter.stop();
  });

  it('stops on hide and drops the first interval after showing again', () => {
    const fake = fakeEnv();
    const meter = startFrameMeter(fake.env);
    const end = fake.frames(0, [16, 16]);
    fake.setVisible(false);
    expect(fake.hasPending()).toBe(false);
    fake.setVisible(true);
    // 10 s hidden: the first frame after showing only restarts the clock.
    fake.frames(end + 10_000, [17]);
    expect(meter.take()).toEqual({ count: 3, slow: 0, p95_ms: 17 });
    meter.stop();
    expect(fake.hasPending()).toBe(false);
  });
});
