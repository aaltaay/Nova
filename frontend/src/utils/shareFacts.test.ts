import { describe, expect, it } from 'vitest';
import {
  fmtFloat,
  fmtSettlementDate,
  fmtSettlementDateShort,
  fmtShortInterest,
  floatTitle,
  shortInterestTitle,
} from './shareFacts';
import { FLOAT_CONTRADICTED_FALLBACK } from '../constantGroups/share_facts';

/** FINRA's 2026-08-31 settlement as Yahoo stamps it: midnight UTC. */
const AUG_31 = Date.UTC(2026, 7, 31) / 1000;
const WHLR_REASON =
  'Float 54K is under half of the 568K shares not held by insiders (568K outstanding, 0% insiders) -- likely stale since a dilution';

describe('the settlement date (#532)', () => {
  it('reads the UTC date Yahoo stamped, never the Eastern evening before', () => {
    expect(fmtSettlementDate(AUG_31)).toBe('Aug 31');
    expect(fmtSettlementDateShort(AUG_31)).toBe('8/31');
  });

  it('is unknown without a date', () => {
    expect(fmtSettlementDate(null)).toBeNull();
    expect(fmtSettlementDate(undefined)).toBeNull();
    expect(fmtSettlementDateShort(Number.NaN)).toBeNull();
  });
});

describe('a contradicted float (#532)', () => {
  it('reads "54.0K?" with the reason on hover', () => {
    expect(fmtFloat(54_000, true)).toBe('54.0K?');
    expect(floatTitle(true, WHLR_REASON)).toBe(WHLR_REASON);
    expect(floatTitle(true, null)).toBe(FLOAT_CONTRADICTED_FALLBACK);
  });

  it('reads as it always did when the float checks out or cannot be checked', () => {
    expect(fmtFloat(54_000, false)).toBe('54.0K');
    expect(fmtFloat(54_000, null)).toBe('54.0K');
    expect(fmtFloat(54_000, undefined)).toBe('54.0K');
    expect(floatTitle(false, WHLR_REASON)).toBeUndefined();
    expect(floatTitle(null, null)).toBeUndefined();
  });

  it('marks no unknown float', () => {
    expect(fmtFloat(null, true)).toBe('—');
  });
});

describe('short interest with its date and basis (#532)', () => {
  it('carries the settlement date', () => {
    expect(fmtShortInterest(566_000, AUG_31)).toBe('566.0K (Aug 31)');
    expect(fmtShortInterest(566_000, null)).toBe('566.0K');
    expect(fmtShortInterest(null, AUG_31)).toBe('—');
  });

  it('names the date, the source and Yahoo\'s ratio on hover', () => {
    const title = shortInterestTitle(566_000, AUG_31, 6.9)!;
    expect(title).toContain('Short interest 566.0K, FINRA settlement Aug 31, 2026');
    expect(title).toContain('Yahoo, from FINRA');
    expect(title).toContain("Short ratio 6.9 is Yahoo's own");
    expect(title).toContain("not FINRA's days to cover");
    expect(shortInterestTitle(566_000, null)).toContain('settlement date not reported');
    expect(shortInterestTitle(null, null, null)).toBeUndefined();
  });
});
