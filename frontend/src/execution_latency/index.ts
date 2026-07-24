/** Public execution-latency feature API (ADR 005). */
export {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  clientTimingHeaders,
} from './browserTiming';
export type {
  BrowserExecutionTiming,
  BrowserTimingClock,
} from './browserTiming';
export { LatencyDashboard } from './LatencyDashboard';
export { parseTimedExecutionResponse } from './responseOutcome';
export type {
  BrowserActionStamp,
  BrowserTimingSample,
  ClientTimingPayload,
} from './types';
