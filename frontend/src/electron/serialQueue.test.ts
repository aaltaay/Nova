import { describe, expect, it } from 'vitest';
import { createSerialQueue, createSharedRun } from '../../electron/serialQueue.mjs';

describe('createSerialQueue', () => {
  it('runs enqueued work in order and joins overlapping jobs', async () => {
    const queue = createSerialQueue();
    const seen: number[] = [];
    const first = queue.enqueue(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      seen.push(1);
      return 'one';
    });
    const second = queue.enqueue(async () => {
      seen.push(2);
      return 'two';
    });
    await expect(Promise.all([first, second])).resolves.toEqual(['one', 'two']);
    expect(seen).toEqual([1, 2]);
  });
});

describe('createSharedRun', () => {
  it('gives a call made while a run is going that same run, never a second one', async () => {
    // 2026-09-29: "Restart backend now" and the header's API-down auto-heal each asked for a
    // reload; queued one after the other, the second stopped the engine the first brought up.
    let runs = 0;
    let finish: (value: string) => void = () => {};
    const shared = createSharedRun(() => {
      runs += 1;
      return new Promise<string>((resolve) => {
        finish = resolve;
      });
    });
    const operator = shared.run();
    const autoHeal = shared.run();
    expect(autoHeal).toBe(operator);
    expect(shared.running()).toBe(true);
    await Promise.resolve();
    finish('v1030');
    await expect(Promise.all([operator, autoHeal])).resolves.toEqual(['v1030', 'v1030']);
    expect(runs).toBe(1);
    expect(shared.running()).toBe(false);
  });

  it('starts afresh once the run settled, a failed one included', async () => {
    let runs = 0;
    const shared = createSharedRun(async () => {
      runs += 1;
      if (runs === 1) throw new Error('Not restarted');
      return 'ok';
    });
    await expect(shared.run()).rejects.toThrow('Not restarted');
    expect(shared.running()).toBe(false);
    await expect(shared.run()).resolves.toBe('ok');
    expect(runs).toBe(2);
  });
});
