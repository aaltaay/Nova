/**
 * @vitest-environment jsdom
 *
 * The Market blocks' remembered switches (ADR 053): a known shape reads back, anything else falls back to 1 D /
 * biggest names field by field, and blocked storage never breaks the page.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MARKET_PERIODS_STORAGE_KEY } from './constants';
import { DEFAULT_PERIODS, parsePeriods, readPeriods, writePeriods } from './periods';
import { signedPct, price, until } from './format';

describe('market periods', () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('round-trips a written choice', () => {
    const p = { sectors: '7D', industries: '30D', climate: '7D', top: { kind: 'runners', period: '30D' } } as const;
    writePeriods(p);
    expect(JSON.parse(window.localStorage.getItem(MARKET_PERIODS_STORAGE_KEY) ?? '{}').schema_version).toBe(1);
    expect(readPeriods()).toEqual(p);
  });

  it('refuses another schema version and unknown values', () => {
    expect(parsePeriods({ schema_version: 2, sectors: '7D' })).toEqual(DEFAULT_PERIODS);
    expect(parsePeriods({ schema_version: 1, sectors: '2W', climate: '30D', top: { kind: 'hot', period: '7D' } }))
      .toEqual({ ...DEFAULT_PERIODS, climate: '30D', top: { kind: 'biggest', period: '7D' } });
    // Movers was retired on 2026-10-14: a saved Movers choice opens on the biggest names.
    expect(parsePeriods({ schema_version: 1, top: { kind: 'movers', period: '1D' } }).top.kind).toBe('biggest');
    expect(parsePeriods(null)).toEqual(DEFAULT_PERIODS);
  });

  it('survives blocked storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readPeriods()).toEqual(DEFAULT_PERIODS);
    expect(() => writePeriods(DEFAULT_PERIODS)).not.toThrow();
  });
});

describe('market number words', () => {
  it('never shows an unknown as zero', () => {
    expect(signedPct(null)).toBe('--');
    expect(signedPct(1.48)).toBe('+1.48%');
    expect(signedPct(-0.5)).toBe('−0.50%');
    expect(price(47215)).toBe('47,215');
    expect(price(6842.5)).toBe('6,842.50');
    expect(until(6 * 3600 + 8 * 60)).toBe('6 h 08 m');
  });
});
