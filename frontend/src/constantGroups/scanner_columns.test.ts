import { describe, expect, it } from 'vitest';
import {
  LARGE_CAP_COLUMNS,
  SCANNER_COLUMNS,
  SCANNER_EARNINGS_COLUMN,
  SCANNER_NEWS_COLUMN,
} from './scanner_columns';

function columnFor(
  columns: [string, string][],
  key: string,
): [string, string] | undefined {
  return columns.find(([k]) => k === key);
}

describe('shared scanner News and Earnings columns', () => {
  it('uses the same News and Earnings tuples on Gainers and Large Cap', () => {
    expect(columnFor(SCANNER_COLUMNS, 'newest_headline_at')).toBe(SCANNER_NEWS_COLUMN);
    expect(columnFor(SCANNER_COLUMNS, 'earnings_day_offset')).toBe(SCANNER_EARNINGS_COLUMN);
    expect(columnFor(LARGE_CAP_COLUMNS, 'newest_headline_at')).toBe(SCANNER_NEWS_COLUMN);
    expect(columnFor(LARGE_CAP_COLUMNS, 'earnings_day_offset')).toBe(SCANNER_EARNINGS_COLUMN);
  });

  it('keeps the Large Cap swing countdown as Days, not a second Earnings header', () => {
    expect(columnFor(LARGE_CAP_COLUMNS, 'days_to_earnings')).toEqual([
      'days_to_earnings',
      'Days',
    ]);
    expect(SCANNER_EARNINGS_COLUMN[1]).toBe('Earnings');
  });
});
