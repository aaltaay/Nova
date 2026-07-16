import { describe, expect, it } from 'vitest';
import { maskSecret } from './maskSecret';

describe('maskSecret', () => {
  it('masks long secrets showing trailing chars', () => {
    expect(maskSecret('abcdefghijklmnop')).toBe('************mnop');
  });

  it('fully masks short secrets', () => {
    expect(maskSecret('abc')).toBe('***');
  });

  it('returns empty for missing value', () => {
    expect(maskSecret(null)).toBe('');
    expect(maskSecret('')).toBe('');
  });
});
