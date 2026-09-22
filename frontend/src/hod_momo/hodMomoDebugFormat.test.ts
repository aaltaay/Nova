import { describe, expect, it } from 'vitest';
import {
  fmtEnrichedAgo,
  fmtPctPoints,
  fmtTimes,
  fmtUsd,
  inspectErrorText,
  readInspectReply,
} from './hodMomoDebugFormat';

describe('HOD debug formatting', () => {
  it('states an absent figure as a bare dash, never "—x" or "—%" (QA C67)', () => {
    expect(fmtTimes(null)).toBe('—');
    expect(fmtTimes(2.345)).toBe('2.35x');
    expect(fmtPctPoints(undefined)).toBe('—');
    expect(fmtPctPoints(12.3)).toBe('12.30%');
    expect(fmtUsd(Number.NaN)).toBe('—');
    expect(fmtUsd(109.02)).toBe('$109.02');
  });

  it('ages an epoch enrichment stamp and refuses a monotonic one (QA C34)', () => {
    const now = 1_790_050_000;
    expect(fmtEnrichedAgo(now - 12, now)).toBe('12s ago');
    expect(fmtEnrichedAgo(now - 600, now)).toBe('10m ago');
    expect(fmtEnrichedAgo(now - 3 * 3600, now)).toBe('3h ago');
    // An older backend sent time.monotonic(): "1790012783s ago" -- stated as unknown.
    expect(fmtEnrichedAgo(37_217, now)).toBe('—');
    expect(fmtEnrichedAgo(now + 30, now)).toBe('—');
    expect(fmtEnrichedAgo(0, now)).toBe('—');
  });
});

describe('Symbol Inspector replies (QA C10)', () => {
  it('refuses a 404 body with no snap instead of crashing on snap.price', () => {
    expect(readInspectReply({ detail: 'Not Found' })).toBeNull();
    expect(readInspectReply(null)).toBeNull();
    expect(inspectErrorText(404, { detail: 'Not Found' })).toBe('Inspector: Not Found (HTTP 404)');
    expect(inspectErrorText(500, 'x')).toBe('Inspector: request failed (HTTP 500)');
    expect(inspectErrorText(200, {})).toMatch(/not a symbol snapshot/);
  });

  it('accepts a snapshot and defaults a missing decision list', () => {
    const reply = readInspectReply({ symbol: 'GRML', snap: { price: 9.42 }, session_high: null });
    expect(reply?.decisions).toEqual([]);
    expect(reply?.would_fire_now).toBeNull();
  });
});
