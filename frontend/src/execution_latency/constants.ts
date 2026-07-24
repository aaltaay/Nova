export const LATENCY_METRICS_POLL_MS = 5_000;
export const LATENCY_DATA_STALE_MS = 15_000;
export const LATENCY_MAX_OPERATION_ROWS = 96;
export const LATENCY_MAX_SEGMENT_ROWS = 64;
export const BROWSER_TIMING_RING_SIZE = 32;
export const BROWSER_VISIBLE_FRAME_COUNT = 2;

export const EXECUTION_LATENCY_PATH = '/api/ibkr/execution-latency';
export const OPERATION_METRICS_PATH = '/api/metrics/ops';

export const BROWSER_TIMING_CLOCK_LABEL =
  'performance.now() — same document only';
export const BACKEND_TIMING_CLOCK_LABEL =
  'perf_counter_ns — same process boot only';
export const WALL_CLOCK_LIMITATION =
  'Paired wall clocks include clock offset plus transport; they are not latency.';
