import { describe, expect, it, vi } from 'vitest';
import { createRafCoalesce } from './rafCoalesce';

describe('createRafCoalesce', () => {
  it('merges many schedule() calls into one flush per frame', () => {
    vi.useFakeTimers();
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 16) as unknown as number,
    );
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));

    let n = 0;
    const raf = createRafCoalesce(() => {
      n += 1;
    });
    raf.schedule();
    raf.schedule();
    raf.schedule();
    expect(n).toBe(0);
    expect(raf.scheduled()).toBe(true);
    vi.advanceTimersByTime(16);
    expect(n).toBe(1);
    expect(raf.scheduled()).toBe(false);

    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('flushNow runs immediately and cancels a pending frame', () => {
    vi.useFakeTimers();
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 16) as unknown as number,
    );
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));

    let n = 0;
    const raf = createRafCoalesce(() => {
      n += 1;
    });
    raf.schedule();
    raf.flushNow();
    expect(n).toBe(1);
    vi.advanceTimersByTime(16);
    expect(n).toBe(1);

    vi.unstubAllGlobals();
    vi.useRealTimers();
  });
});
