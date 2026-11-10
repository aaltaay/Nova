import { describe, expect, it } from 'vitest';
import {
  FAILED_ROUND_TRIP_MS,
  Rolling,
  apiBaseFor,
  bestClock,
  clockSample,
  epochMs,
  frameAgeMs,
  linkVerdict,
  wsBaseFor,
} from './linkStats';

describe('where the API is', () => {
  it('is the local API for a page this PC serves', () => {
    for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
      expect(apiBaseFor({ protocol: 'http:', hostname })).toBe('http://127.0.0.1:8000');
    }
    expect(apiBaseFor({ protocol: 'file:', hostname: '' })).toBe('http://127.0.0.1:8000');
  });

  it("is the tunnel's API port on the page's own name, and its sockets are secure", () => {
    const base = apiBaseFor({ protocol: 'https:', hostname: 'Desk.tail1234.ts.net' });
    expect(base).toBe('https://desk.tail1234.ts.net:8443');
    expect(wsBaseFor(base)).toBe('wss://desk.tail1234.ts.net:8443');
    expect(wsBaseFor('http://127.0.0.1:8000')).toBe('ws://127.0.0.1:8000');
  });
});

describe("the phone's clock against the PC's", () => {
  it('reads the offset at the middle of the round trip', () => {
    // The phone is 2 s behind the PC; the round trip took 80 ms.
    const sample = clockSample(1_000_000, 1_000_080, (1_000_040 + 2_000) / 1000);
    expect(sample.rttMs).toBe(80);
    expect(sample.offsetMs).toBeCloseTo(2_000, 6);
  });

  it('keeps the quickest round trip', () => {
    const slow = { rttMs: 400, offsetMs: 2_150 };
    const quick = { rttMs: 40, offsetMs: 2_004 };
    expect(bestClock([slow, quick, { rttMs: 90, offsetMs: 1_990 }])).toBe(quick);
    expect(bestClock([])).toBeNull();
  });

  it('ages a frame on the corrected clock, so a wrong phone clock does not hide lag', () => {
    // Sent at PC time 1,700,000,000.000; arrives 120 ms later on a phone whose clock is 2 s behind.
    const sent = 1_700_000_000.0;
    const arrivedOnPhone = sent * 1000 + 120 - 2_000;
    expect(frameAgeMs(arrivedOnPhone, 2_000, sent)).toBeCloseTo(120, 3);
    expect(frameAgeMs(arrivedOnPhone, 2_000, null)).toBeNull();
  });

  it('reads seconds and milliseconds epochs', () => {
    expect(epochMs(1_700_000_000.5)).toBe(1_700_000_000_500);
    expect(epochMs(1_700_000_000_500)).toBe(1_700_000_000_500);
    expect(epochMs('x')).toBeNull();
  });
});

describe('a measure over the window', () => {
  it('reads the middle, the 95th and the worst, and forgets what left the window', () => {
    const rolling = new Rolling(10_000);
    for (let i = 1; i <= 100; i += 1) rolling.add(i * 10, i, 50);
    expect(rolling.spread(1_000)).toEqual({ n: 100, p50: 50, p95: 95, max: 100 });
    expect(rolling.rate(1_000)).toEqual({ perSec: 100, bytesPerSec: 5_000 });
    expect(rolling.spread(10_995)?.n).toBe(1);
    expect(rolling.spread(20_000)).toBeNull();
  });

  it('counts a frame with no age in the rate and not in the spread', () => {
    const rolling = new Rolling(10_000);
    rolling.add(0, null, 10);
    rolling.add(500, 40, 10);
    expect(rolling.spread(500)?.n).toBe(1);
    expect(rolling.rate(500).perSec).toBe(2);
  });
});

describe('the verdict', () => {
  const spread = (p95: number) => ({ n: 10, p50: p95 / 2, p95, max: p95 });

  it('waits for both measures, then passes only when both are under the limit', () => {
    expect(linkVerdict(null, spread(100))).toBe('waiting');
    expect(linkVerdict(spread(100), null)).toBe('waiting');
    expect(linkVerdict(spread(120), spread(90))).toBe('pass');
    expect(linkVerdict(spread(620), spread(90))).toBe('fail');
    expect(linkVerdict(spread(120), spread(501))).toBe('fail');
  });

  it('fails a link that drops round trips, however quick the ones that got through', () => {
    // 9 in 10 answer in 40 ms; 1 in 10 times out. Left out, the timeouts would read as a clean pass.
    const roundTrip = new Rolling(60_000);
    for (let i = 0; i < 30; i += 1) roundTrip.add(i * 1000, i % 10 === 0 ? FAILED_ROUND_TRIP_MS : 40);
    const got = roundTrip.spread(30_000);
    expect(got?.n).toBe(30);
    expect(got?.p50).toBe(40);
    expect(linkVerdict(spread(120), got)).toBe('fail');
  });
});
