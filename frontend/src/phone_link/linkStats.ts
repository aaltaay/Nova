/**
 * The arithmetic of the phone link test (ADR 070): where the API is from this page, the phone's
 * clock against the PC's, and the spread of a measure over the last few seconds. Pure, no DOM.
 *
 * Every frame's age is "the PC's clock when it was sent" against "the PC's clock now", so the
 * phone's own clock is first corrected by the offset the round trips measure. A round trip's
 * offset is only as good as half its travel time, so the quickest one is kept.
 */

/** The order door refuses a new entry that arrives later than this after the tap (backend ORDER_MAX_ARRIVAL_MS). */
export const LINK_LIMIT_MS = 500;
/** How long a round trip may take before the page gives up on it. */
export const PING_TIMEOUT_MS = 5_000;
/**
 * What a round trip that failed counts as: one that timed out, was refused or could not be read is a
 * round trip of the full timeout, never a missing sample -- or a link that drops half its requests
 * would be judged on the half that got through.
 */
export const FAILED_ROUND_TRIP_MS = PING_TIMEOUT_MS;
/** How far back each measure's spread reads. */
export const LINK_WINDOW_MS = 30_000;
/** Round trips kept for the clock offset. */
export const CLOCK_SAMPLES_KEEP = 20;

const LOCAL_API_BASE = 'http://127.0.0.1:8000';
/** The tunnel serves the page on 443 and the API, whole, on this port of the same name (docs/phone-link.md). */
export const TUNNEL_API_PORT = 8443;

/**
 * The API for a page at *loc*. A page this PC serves (the Vite desk, a file) talks to the local API;
 * a page reached by any other name came through the tunnel, which serves the API on the same name.
 */
export function apiBaseFor(loc: { protocol: string; hostname: string }): string {
  const host = loc.hostname.toLowerCase();
  const local = host === 'localhost' || host === '[::1]' || host === '::1' || host.startsWith('127.') || host === '';
  if (local || !loc.protocol.startsWith('http')) return LOCAL_API_BASE;
  return `https://${host}:${TUNNEL_API_PORT}`;
}

export function wsBaseFor(apiBase: string): string {
  return apiBase.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://');
}

export interface ClockSample {
  /** Request out and answer back, ms. */
  rttMs: number;
  /** The PC's clock minus this device's, ms, as this round trip read it (good to half `rttMs`). */
  offsetMs: number;
}

/** One round trip: this device's clock when it asked and when the answer came, and the PC's clock in the answer. */
export function clockSample(askedWallMs: number, answeredWallMs: number, serverEpochSec: number): ClockSample {
  const rttMs = Math.max(0, answeredWallMs - askedWallMs);
  return { rttMs, offsetMs: serverEpochSec * 1000 - (askedWallMs + answeredWallMs) / 2 };
}

/** The offset from the quickest round trip, or null before the first. */
export function bestClock(samples: readonly ClockSample[]): ClockSample | null {
  let best: ClockSample | null = null;
  for (const s of samples) if (best == null || s.rttMs < best.rttMs) best = s;
  return best;
}

/** An epoch the backend sent, as ms: its frames carry seconds, a few fields carry ms. */
export function epochMs(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null;
  return value > 1e11 ? value : value * 1000;
}

/** How old a frame is on arrival: the PC's clock now (this device's, corrected) minus the PC's clock when sent. */
export function frameAgeMs(arrivedWallMs: number, offsetMs: number, sentEpoch: unknown): number | null {
  const sent = epochMs(sentEpoch);
  return sent == null ? null : arrivedWallMs + offsetMs - sent;
}

export interface Spread {
  n: number;
  p50: number;
  p95: number;
  max: number;
}

function percentile(sorted: readonly number[], p: number): number {
  const i = Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1));
  return sorted[i];
}

/** A measure's values over the last `windowMs`, and how many frames and bytes carried them. */
export class Rolling {
  private readonly at: number[] = [];
  private readonly values: number[] = [];
  private readonly bytes: number[] = [];
  private readonly windowMs: number;

  constructor(windowMs: number = LINK_WINDOW_MS) {
    this.windowMs = windowMs;
  }

  add(nowMs: number, value: number | null, bytes = 0): void {
    this.at.push(nowMs);
    this.values.push(value ?? Number.NaN);
    this.bytes.push(bytes);
    this.trim(nowMs);
  }

  private trim(nowMs: number): void {
    let drop = 0;
    while (drop < this.at.length && nowMs - this.at[drop] > this.windowMs) drop += 1;
    if (drop) {
      this.at.splice(0, drop);
      this.values.splice(0, drop);
      this.bytes.splice(0, drop);
    }
  }

  spread(nowMs: number): Spread | null {
    this.trim(nowMs);
    const sorted = this.values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
    if (!sorted.length) return null;
    return { n: sorted.length, p50: percentile(sorted, 0.5), p95: percentile(sorted, 0.95), max: sorted[sorted.length - 1] };
  }

  /** Frames and bytes per second over the window so far (at least one second, so a first frame is not a spike). */
  rate(nowMs: number): { perSec: number; bytesPerSec: number } {
    this.trim(nowMs);
    if (!this.at.length) return { perSec: 0, bytesPerSec: 0 };
    const span = Math.max(1000, Math.min(this.windowMs, nowMs - this.at[0])) / 1000;
    const bytes = this.bytes.reduce((sum, b) => sum + b, 0);
    return { perSec: this.at.length / span, bytesPerSec: bytes / span };
  }
}

export type Verdict = 'pass' | 'fail' | 'waiting';

/** Under the limit only when 95 in 100 of both the data and the round trip are; waiting until both were measured. */
export function linkVerdict(feed: Spread | null, roundTrip: Spread | null, limitMs = LINK_LIMIT_MS): Verdict {
  if (!feed || !roundTrip) return 'waiting';
  return feed.p95 <= limitMs && roundTrip.p95 <= limitMs ? 'pass' : 'fail';
}
