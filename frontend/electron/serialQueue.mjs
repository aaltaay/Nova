/**
 * FIFO async lock. Concurrent start/restart calls share one chain so a second
 * nova:restartApi cannot spawn a second run_api.py while the first is stopping.
 */

export function createSerialQueue() {
  let tail = Promise.resolve();

  return {
    /**
     * @template T
     * @param {() => T | Promise<T>} fn
     * @returns {Promise<T>}
     */
    enqueue(fn) {
      const run = tail.then(
        () => fn(),
        () => fn(),
      );
      tail = run.then(
        () => undefined,
        () => undefined,
      );
      return run;
    },
  };
}

/**
 * Collapse overlapping calls into one run: a call made while `fn` is still running gets that
 * run's promise instead of starting another. The next call after it settles starts afresh.
 * @template T
 * @param {() => Promise<T>} fn
 * @returns {{ run: () => Promise<T>, running: () => boolean }}
 */
export function createSharedRun(fn) {
  let current = null;
  return {
    run() {
      if (current) return current;
      const started = Promise.resolve().then(fn);
      current = started;
      const clear = () => {
        if (current === started) current = null;
      };
      started.then(clear, clear);
      return started;
    },
    running: () => current !== null,
  };
}
