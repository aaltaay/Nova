import { describe, expect, it } from 'vitest';
import { formatTrailKind, formatTrailMoney, formatTrailState } from './formatTrail';

describe('formatTrailMoney', () => {
  it('does not paint missing commission as $0', () => {
    expect(formatTrailMoney(null)).toBe('--');
    expect(formatTrailMoney(undefined)).toBe('--');
    expect(formatTrailMoney(2.25)).toBe('$2.25');
    expect(formatTrailMoney(-1)).toBe('-$1.00');
  });
});

describe('formatTrailKind', () => {
  it('labels stored trail steps', () => {
    expect(formatTrailKind('place')).toBe('Place');
    expect(formatTrailKind('flatten')).toBe('Flatten');
    expect(formatTrailKind('commission')).toBe('Commission');
    expect(formatTrailKind('close')).toBe('Close');
  });
});

describe('formatTrailState', () => {
  it('keeps import rows unlabeled when journal did not stamp net/gross', () => {
    expect(formatTrailState({ kind: 'closed', pnl_basis: null })).toBe('closed');
    expect(formatTrailState({ kind: 'closed', pnl_basis: 'gross' })).toBe('closed · gross');
    expect(formatTrailState({ kind: 'open', pnl_basis: null })).toBe('open');
  });
});