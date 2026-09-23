/**
 * Frame pacing for this window's performance report (ADR 026): the interval
 * between animation frames, measured only while the window is visible. A
 * hidden window's frames are throttled or stopped by the browser and say
 * nothing about jank, so the loop stops when the page hides and restarts when
 * it shows -- dropping the first interval after the restart, which spans the
 * hidden time. Intervals go into a fixed buffer; nothing allocates per frame.
 */
import { PERF_FRAME_SAMPLES_MAX, PERF_SLOW_FRAME_MS } from '../constantGroups/perf';

export interface FrameStats {
  count: number;
  slow: number;
  p95_ms: number | null;
}

/** The browser calls the meter needs; a test passes a synthetic clock. */
export interface FrameMeterEnv {
  requestFrame: (cb: (ts: number) => void) => number;
  cancelFrame: (id: number) => void;
  isVisible: () => boolean;
  /** Subscribe to visibility changes; returns the unsubscribe. */
  onVisibilityChange: (cb: () => void) => () => void;
}

export interface FrameMeter {
  /** This interval's frames, then zero; null when no frame was measured. */
  take: () => FrameStats | null;
  stop: () => void;
}

function browserEnv(): FrameMeterEnv | null {
  if (typeof document === 'undefined' || typeof requestAnimationFrame !== 'function') return null;
  return {
    requestFrame: (cb) => requestAnimationFrame(cb),
    cancelFrame: (id) => cancelAnimationFrame(id),
    isVisible: () => document.visibilityState === 'visible',
    onVisibilityChange: (cb) => {
      document.addEventListener('visibilitychange', cb);
      return () => document.removeEventListener('visibilitychange', cb);
    },
  };
}

/** Nearest-rank 95th percentile of the first `n` values (sorts a copy). */
export function p95(values: Float64Array, n: number): number | null {
  if (n <= 0) return null;
  const sorted = values.slice(0, n).sort();
  return sorted[Math.ceil(0.95 * n) - 1];
}

const NO_FRAMES: FrameMeter = { take: () => null, stop: () => {} };

export function startFrameMeter(env: FrameMeterEnv | null = browserEnv()): FrameMeter {
  if (!env) return NO_FRAMES;
  const samples = new Float64Array(PERF_FRAME_SAMPLES_MAX);
  let kept = 0;
  let count = 0;
  let slow = 0;
  let last: number | null = null;
  let frameId: number | null = null;

  const record = (interval: number) => {
    count += 1;
    if (interval > PERF_SLOW_FRAME_MS) slow += 1;
    if (kept < samples.length) samples[kept++] = interval;
  };

  const loop = (ts: number) => {
    frameId = null;
    if (!env.isVisible()) {
      last = null;
      return;
    }
    if (last !== null) record(ts - last);
    last = ts;
    frameId = env.requestFrame(loop);
  };

  const resume = () => {
    if (frameId !== null) return;
    last = null;
    frameId = env.requestFrame(loop);
  };

  const pause = () => {
    if (frameId !== null) env.cancelFrame(frameId);
    frameId = null;
    last = null;
  };

  const unsubscribe = env.onVisibilityChange(() => {
    if (env.isVisible()) resume();
    else pause();
  });
  if (env.isVisible()) resume();

  return {
    take() {
      if (count === 0) return null;
      const p = p95(samples, kept);
      const stats = { count, slow, p95_ms: p === null ? null : Math.round(p * 10) / 10 };
      kept = 0;
      count = 0;
      slow = 0;
      return stats;
    },
    stop() {
      unsubscribe();
      pause();
    },
  };
}
