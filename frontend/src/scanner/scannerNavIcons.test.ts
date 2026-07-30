import { describe, expect, it } from 'vitest';
import { formatScannerNavCount } from './scannerNavIcons';

describe('formatScannerNavCount', () => {
  it('hides zero and caps at 99+', () => {
    expect(formatScannerNavCount(0)).toBe('');
    expect(formatScannerNavCount(7)).toBe('7');
    expect(formatScannerNavCount(99)).toBe('99');
    expect(formatScannerNavCount(100)).toBe('99+');
  });
});
