import { describe, expect, it } from 'vitest';
import { readLuldTrail } from './luldTrail';

const BODY = {
  schema_version: 1, symbol: 'grml', source: 'replay', state: 'bands', reason: null, tier_sure: true,
  watching_since: 100, as_of: 400,
  steps: [
    { ts: 100, lower: 14.18, upper: 17.33, exact: true },
    { ts: 200, lower: null, upper: null, exact: false },
    { ts: 300, lower: 13.5, upper: 16.5, exact: false },
  ],
};

describe('readLuldTrail', () => {
  it('reads a version-1 trail, its steps in time order', () => {
    const t = readLuldTrail(BODY);
    expect(t?.symbol).toBe('GRML');
    expect(t?.source).toBe('replay');
    expect(t?.steps.map(s => [s.ts, s.lower, s.upper, s.exact])).toEqual([
      [100, 14.18, 17.33, true], [200, null, null, false], [300, 13.5, 16.5, false],
    ]);
  });

  it('refuses another version or a body without steps or a clock', () => {
    expect(readLuldTrail({ ...BODY, schema_version: 2 })).toBeNull();
    expect(readLuldTrail({ ...BODY, steps: undefined })).toBeNull();
    expect(readLuldTrail({ ...BODY, as_of: null })).toBeNull();
    expect(readLuldTrail('nope')).toBeNull();
  });

  it('drops a step out of order or without a time, and reads an unsure tier', () => {
    const t = readLuldTrail({ ...BODY, tier_sure: false, steps: [BODY.steps[2], BODY.steps[0], { lower: 1 }] });
    expect(t?.steps.map(s => s.ts)).toEqual([300]);
    expect(t?.tier_sure).toBe(false);
  });
});
