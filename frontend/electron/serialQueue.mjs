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
