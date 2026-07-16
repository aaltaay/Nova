import { describe, expect, it } from 'vitest';
import { fmtPct, fmtRMultiple } from './format';

describe('fmtRMultiple', () => {
  it('formats positive and negative R values', () => {
    expect(fmtRMultiple(2)).toBe('+2.00R');
    expect(fmtRMultiple(-0.5)).toBe('-0.50R');
  });

  it('returns dash for missing values', () => {
    expect(fmtRMultiple(null)).toBe('—');
    expect(fmtRMultiple(undefined)).toBe('—');
  });
});

describe('fmtPct', () => {
  it('formats percentages with one decimal', () => {
    expect(fmtPct(58.3)).toBe('58.3%');
  });

  it('returns dash for missing values', () => {
    expect(fmtPct(null)).toBe('—');
  });
});
