import { describe, expect, it } from 'vitest';
import { parseAutoRecordStatus } from './autoRecordStatusParse';

const windows = {
  open: 'setups',
  setups: { open: true, start: '07:00', end: '15:30', error: null,
    by_setup: [{ setup: 'flat_top_5m', start: '07:00', end: '15:30', open: true }, { setup: 7 }] },
  leaders: { open: false, start: '07:00', end: '10:00' },
};

describe('parseAutoRecordStatus (operator ask 2026-10-14)', () => {
  it('keeps the switch, the windows, why and setup', () => {
    const got = parseAutoRecordStatus({
      active: true, window: 'setups only', symbols: ['COHQ'], yielded: [], last_error: null,
      why: { COHQ: 'near', BAD: 3 }, setup: { COHQ: 'flat_top_5m' }, windows,
      switch: { mode: 'off_today', source: 'operator', day: '2026-10-14', until: 1_760_515_200, error: null },
    });
    expect(got?.switch).toEqual({ mode: 'off_today', source: 'operator', day: '2026-10-14', until: 1_760_515_200, error: null });
    expect(got?.why).toEqual({ COHQ: 'near' });
    expect(got?.setup).toEqual({ COHQ: 'flat_top_5m' });
    expect(got?.windows?.setups.by_setup).toEqual([{ setup: 'flat_top_5m', start: '07:00', end: '15:30', open: true }]);
  });

  it('leaves out a switch or windows it cannot read, never drawing them On', () => {
    const got = parseAutoRecordStatus({ active: false, symbols: 'X', switch: { mode: 'maybe', source: 'operator' },
      windows: { open: 'sometimes', setups: {}, leaders: {} } });
    expect(got).toEqual({ active: false, window: '', symbols: [], yielded: [], last_error: null });
    expect(parseAutoRecordStatus(null)).toBeNull();
  });
});
