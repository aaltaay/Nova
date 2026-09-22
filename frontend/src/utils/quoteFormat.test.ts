import { describe, expect, it } from 'vitest';
import {
  fmtMarketCap,
  fmtPct,
  fmtPrice,
  fmtRvol,
  fmtSessionPrice,
  fmtVolume,
  pctToneClass,
  sessionPriceOrNull,
} from './quoteFormat';

describe('sessionPriceOrNull / fmtSessionPrice', () => {
  it('treats null and undefined as missing', () => {
    expect(sessionPriceOrNull(null)).toBeNull();
    expect(sessionPriceOrNull(undefined)).toBeNull();
    expect(fmtSessionPrice(null)).toBe('—');
  });

  it('treats 0 and negative as missing (never "$0.00")', () => {
    expect(sessionPriceOrNull(0)).toBeNull();
    expect(sessionPriceOrNull(-1)).toBeNull();
    expect(fmtSessionPrice(0)).toBe('—');
  });

  it('formats positive session prices', () => {
    expect(sessionPriceOrNull(8.28)).toBe(8.28);
    expect(fmtSessionPrice(8.28)).toBe('$8.28');
  });
});

describe('zero and near-zero moves are flat (QA W21)', () => {
  it('never prints -0.00% or +0.00%', () => {
    expect(fmtPct(-0.000025)).toBe('0.00%');
    expect(fmtPct(0.00004)).toBe('0.00%');
    expect(fmtPct(0)).toBe('0.00%');
    expect(fmtPct(0.978)).toBe('+97.80%');
    expect(fmtPct(-0.1671)).toBe('-16.71%');
  });

  it('fits a four-digit move in its column (QA D15)', () => {
    expect(fmtPct(124.9993)).toBe('+12,500%');
    expect(fmtPct(-12.3456)).toBe('-1,235%');
    expect(fmtPct(9.9994)).toBe('+999.94%');
  });

  it('gives a flat figure no tone', () => {
    expect(pctToneClass(0)).toBe('');
    expect(pctToneClass(-0.000025)).toBe('');
    expect(pctToneClass(0.01)).toBe('positive');
    expect(pctToneClass(-0.01)).toBe('negative');
    expect(pctToneClass(null)).toBe('');
  });
});

describe('unit boundaries (QA W22)', () => {
  it('promotes a figure that rounds to 1000 of its unit', () => {
    expect(fmtVolume(999_960)).toBe('1.0M');
    expect(fmtVolume(999_999)).toBe('1.0M');
    expect(fmtVolume(999)).toBe('999');
    expect(fmtVolume(12_400_000)).toBe('12.4M');
    expect(fmtMarketCap(999_950_000)).toBe('$1.00B');
    expect(fmtMarketCap(45_000_000)).toBe('$45.0M');
  });

  it('has a billions unit for share counts', () => {
    expect(fmtVolume(1_234_600_000)).toBe('1.23B');
    expect(fmtVolume(15_000_000_000)).toBe('15.00B');
  });

  it('writes a tiny real RVOL as under 0.01x, never 0x', () => {
    expect(fmtRvol(0)).toBe('<0.01x');
    expect(fmtRvol(0.004)).toBe('<0.01x');
    expect(fmtRvol(12.44)).toBe('12.44x');
    expect(fmtRvol(null)).toBeNull();
  });
});

describe('prices (QA W23, D15)', () => {
  it('keeps sub-penny digits below a dollar', () => {
    expect(fmtPrice(0.678)).toBe('$0.678');
    expect(fmtPrice(0.0512)).toBe('$0.0512');
    expect(fmtPrice(0.5)).toBe('$0.50');
    expect(fmtPrice(1.42)).toBe('$1.42');
  });

  it('separates thousands', () => {
    expect(fmtPrice(12345.6789)).toBe('$12,345.68');
  });
});

