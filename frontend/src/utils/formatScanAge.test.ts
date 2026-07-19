import { describe, expect, it } from 'vitest';
import { formatScanAge } from './formatScanAge';

describe('formatScanAge', () => {
  it('formats seconds under a minute', () => {
    expect(formatScanAge(0)).toBe('0s ago');
    expect(formatScanAge(45)).toBe('45s ago');
  });

  it('formats minutes and hours', () => {
    expect(formatScanAge(90)).toBe('1m ago');
    expect(formatScanAge(3599)).toBe('59m ago');
    expect(formatScanAge(3600)).toBe('1h ago');
    expect(formatScanAge(59915)).toBe('16h ago');
  });

  it('formats multi-day ages', () => {
    expect(formatScanAge(172800)).toBe('2d ago');
  });
});
