import {
  BROWSER_TIMING_RING_SIZE,
  BROWSER_VISIBLE_FRAME_COUNT,
} from './constants';
import type {
  BrowserActionSource,
  BrowserActionStamp,
  BrowserTimingSample,
  ClientTimingPayload,
} from './types';

type Listener = () => void;

export interface BrowserTimingClock {
  wallNow: () => number;
  performanceNow: () => number;
  requestFrame: (callback: FrameRequestCallback) => number;
}

export interface BrowserExecutionTiming {
  clientTimingAtRequest: () => ClientTimingPayload;
  complete: (ok: boolean) => void;
}

const listeners = new Set<Listener>();
const samples: BrowserTimingSample[] = [];

function defaultClock(): BrowserTimingClock {
  return {
    wallNow: () => Date.now(),
    performanceNow: () => performance.now(),
    requestFrame: callback => {
      if (typeof requestAnimationFrame === 'function') {
        return requestAnimationFrame(callback);
      }
      return globalThis.setTimeout(
        () => callback(performance.now()),
        0,
      ) as unknown as number;
    },
  };
}

function safeDelta(end: number, start: number): number | null {
  const delta = end - start;
  return Number.isFinite(delta) && delta >= 0 ? delta : null;
}

function publish(sample: BrowserTimingSample) {
  samples.unshift(sample);
  if (samples.length > BROWSER_TIMING_RING_SIZE) {
    samples.length = BROWSER_TIMING_RING_SIZE;
  }
  listeners.forEach(listener => listener());
}

export function captureBrowserAction(
  source: BrowserActionSource = 'user_action',
  clock: BrowserTimingClock = defaultClock(),
): BrowserActionStamp {
  return {
    wallMs: clock.wallNow(),
    performanceMs: clock.performanceNow(),
    source,
  };
}

export function beginBrowserExecutionTiming(
  operation: string,
  action = captureBrowserAction('client_call'),
  clock: BrowserTimingClock = defaultClock(),
): BrowserExecutionTiming {
  let request: ClientTimingPayload | null = null;
  let responsePerformanceMs: number | null = null;
  let completed = false;

  function clientTimingAtRequest(): ClientTimingPayload {
    if (!request) {
      request = {
        action_wall_ms: action.wallMs,
        action_performance_ms: action.performanceMs,
        request_wall_ms: clock.wallNow(),
        request_performance_ms: clock.performanceNow(),
      };
    }
    return request;
  }

  function complete(ok: boolean) {
    if (completed) return;
    completed = true;
    responsePerformanceMs = clock.performanceNow();
    const timing = clientTimingAtRequest();
    let frames = 0;
    const afterFrame: FrameRequestCallback = () => {
      frames += 1;
      if (frames < BROWSER_VISIBLE_FRAME_COUNT) {
        clock.requestFrame(afterFrame);
        return;
      }
      const visiblePerformanceMs = clock.performanceNow();
      publish({
        operation: operation.slice(0, 64),
        actionSource: action.source,
        outcome: ok ? 'ok' : 'error',
        observedWallMs: clock.wallNow(),
        actionToRequestMs: safeDelta(
          timing.request_performance_ms,
          timing.action_performance_ms,
        ),
        requestToResponseMs: safeDelta(
          responsePerformanceMs!,
          timing.request_performance_ms,
        ),
        responseToVisibleMs: safeDelta(
          visiblePerformanceMs,
          responsePerformanceMs!,
        ),
        requestToVisibleMs: safeDelta(
          visiblePerformanceMs,
          timing.request_performance_ms,
        ),
        clockDomain: 'browser_performance_now_same_document',
      });
    };
    clock.requestFrame(afterFrame);
  }

  return { clientTimingAtRequest, complete };
}

export function clientTimingHeaders(
  timing: BrowserExecutionTiming,
): Headers {
  const value = timing.clientTimingAtRequest();
  const headers = new Headers();
  headers.set('X-Nova-Action-Wall-Ms', String(value.action_wall_ms));
  headers.set(
    'X-Nova-Action-Performance-Ms',
    String(value.action_performance_ms),
  );
  headers.set('X-Nova-Request-Wall-Ms', String(value.request_wall_ms));
  headers.set(
    'X-Nova-Request-Performance-Ms',
    String(value.request_performance_ms),
  );
  return headers;
}

export function getBrowserTimingSamples(): readonly BrowserTimingSample[] {
  return samples;
}

export function subscribeBrowserTiming(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetBrowserTimingForTests() {
  samples.length = 0;
  listeners.clear();
}
