import { describe, expect, it } from 'vitest';
import { createSerialQueue } from '../../electron/serialQueue.mjs';

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
