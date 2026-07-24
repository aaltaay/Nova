import { describe, expect, it, beforeEach } from 'vitest';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  clientTimingHeaders,
  getBrowserTimingSamples,
  resetBrowserTimingForTests,
  type BrowserTimingClock,
} from './browserTiming';

function fakeClock() {
  let wall = 1_700_000_000_000;
  let perf = 100;
  const frames: FrameRequestCallback[] = [];
  const clock: BrowserTimingClock = {
    wallNow: () => wall,
    performanceNow: () => perf,
    requestFrame: callback => {
      frames.push(callback);
      return frames.length;
    },
  };
  return {
    clock,
    set(nextWall: number, nextPerf: number) {
      wall = nextWall;
      perf = nextPerf;
    },
    frame(nextWall: number, nextPerf: number) {
      wall = nextWall;
      perf = nextPerf;
      frames.shift()?.(nextPerf);
    },
  };
}

describe('browser execution timing', () => {
  beforeEach(resetBrowserTimingForTests);

  it('uses browser monotonic deltas and emits paired wall/performance stamps', () => {
    const fake = fakeClock();
    const action = captureBrowserAction('user_action', fake.clock);
    fake.set(1_700_000_005_000, 112);
    const timing = beginBrowserExecutionTiming('manual_place', action, fake.clock);
    const payload = timing.clientTimingAtRequest();
    const headers = clientTimingHeaders(timing);

    fake.set(1_700_000_900_000, 162);
    timing.complete(true);
    fake.frame(1_700_001_500_000, 170);
    fake.frame(1_700_009_000_000, 182);

    expect(payload).toEqual({
      action_wall_ms: 1_700_000_000_000,
      action_performance_ms: 100,
      request_wall_ms: 1_700_000_005_000,
      request_performance_ms: 112,
    });
    expect(headers.get('X-Nova-Request-Performance-Ms')).toBe('112');
    expect(getBrowserTimingSamples()[0]).toMatchObject({
      actionToRequestMs: 12,
      requestToResponseMs: 50,
      responseToVisibleMs: 20,
      requestToVisibleMs: 70,
      actionSource: 'user_action',
    });
  });

  it('never derives duration from wall-clock differences', () => {
    const fake = fakeClock();
    const action = captureBrowserAction('user_action', fake.clock);
    fake.set(100, 90);
    const timing = beginBrowserExecutionTiming('cancel_order', action, fake.clock);
    timing.clientTimingAtRequest();
    fake.set(9_000_000_000_000, 120);
    timing.complete(false);
    fake.frame(1, 125);
    fake.frame(2, 130);

    const sample = getBrowserTimingSamples()[0];
    expect(sample.actionToRequestMs).toBeNull();
    expect(sample.requestToResponseMs).toBe(30);
    expect(sample.responseToVisibleMs).toBe(10);
    expect(sample.outcome).toBe('error');
  });
});
