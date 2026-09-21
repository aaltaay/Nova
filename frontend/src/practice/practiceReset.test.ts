import { describe, expect, it } from 'vitest';
import { parseStartingCash } from './practiceReset';

describe('parseStartingCash', () => {
  it('treats blank as "keep the current starting cash"', () => {
    expect(parseStartingCash('')).toEqual({ ok: true, value: null });
    expect(parseStartingCash('   ')).toEqual({ ok: true, value: null });
  });

  it('accepts whole dollars with $ and thousands separators', () => {
    expect(parseStartingCash('25000')).toEqual({ ok: true, value: 25000 });
    expect(parseStartingCash('$1,000,000')).toEqual({ ok: true, value: 1000000 });
  });

  it('refuses cents, words, negatives and out-of-range amounts', () => {
    for (const raw of ['12.50', 'abc', '-5', '999', '100000001', '1e6']) {
      const parsed = parseStartingCash(raw);
      expect(parsed.ok, raw).toBe(false);
      if (!parsed.ok) expect(parsed.error).toMatch(/\$1,000 and \$100,000,000/);
    }
  });
});
