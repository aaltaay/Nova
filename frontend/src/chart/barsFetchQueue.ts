/**
 * One-at-a-time IBKR historical fetch queue.
 * Timeout / HTTP start after dequeue so four Trader panes do not share one 25s clock.
 */

export interface BarsFetchJob<T> {
  priority: number;
  signal?: AbortSignal;
  run: () => Promise<T>;
}

type PendingJob = {
  priority: number;
  signal?: AbortSignal;
  run: () => Promise<void>;
};

let running = false;
const pending: PendingJob[] = [];

export function resetBarsFetchQueueForTests(): void {
  pending.length = 0;
  running = false;
}

export function pendingBarsFetchCountForTests(): number {
  return pending.length;
}

export function enqueueBarsFetch<T>(job: BarsFetchJob<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const wrapped: PendingJob = {
      priority: job.priority,
      signal: job.signal,
      run: async () => {
        if (job.signal?.aborted) {
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        try {
          resolve(await job.run());
        } catch (err) {
          reject(err);
        }
      },
    };
    const idx = pending.findIndex((item) => item.priority > wrapped.priority);
    if (idx === -1) pending.push(wrapped);
    else pending.splice(idx, 0, wrapped);
    void pumpBarsFetchQueue();
  });
}

async function pumpBarsFetchQueue(): Promise<void> {
  if (running) return;
  const job = pending.shift();
  if (!job) return;
  running = true;
  try {
    await job.run();
  } finally {
    running = false;
    void pumpBarsFetchQueue();
  }
}
