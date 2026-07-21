import { describe, expect, it } from 'vitest';
import { isClosedOrderRecent } from './closedOrderRecency';

const WINDOW = 60_000;
const NOW = Date.parse('2026-07-19T16:00:00.000Z');

describe('isClosedOrderRecent', () => {
  it('highlights completions within the last minute', () => {
    expect(
      isClosedOrderRecent('2026-07-19T15:59:30.000Z', NOW, WINDOW),
    ).toBe(true);
    expect(
      isClosedOrderRecent('2026-07-19T16:00:00.000Z', NOW, WINDOW),
    ).toBe(true);
  });

  it('does not highlight older or missing / invalid times', () => {
    expect(
      isClosedOrderRecent('2026-07-19T15:58:59.000Z', NOW, WINDOW),
    ).toBe(false);
    expect(isClosedOrderRecent(null, NOW, WINDOW)).toBe(false);
    expect(isClosedOrderRecent('not-a-date', NOW, WINDOW)).toBe(false);
  });

  it('ignores future timestamps (clock skew)', () => {
    expect(
      isClosedOrderRecent('2026-07-19T16:00:05.000Z', NOW, WINDOW),
    ).toBe(false);
  });
});
