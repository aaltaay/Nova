import { describe, expect, it } from 'vitest';
import { normalizeIbkrStatus } from './ibkrStatusNormalize';

const GOOD = {
  enabled: true,
  connected: true,
  mode: 'paper',
  venue: 'paper',
  account_id: 'NOVA-PAPER',
  account_ids: ['NOVA-PAPER'],
  capture: true,
  recording: true,
  capture_symbol: 'GDC',
  capture_symbols: ['GDC', 'IMCC'],
  capture_sessions: [{ symbol: 'GDC', counts: {} }],
  capture_resume: [],
  capture_stopped: [{ symbol: 'GRML', at: 1, reason: 'failure', resumed: false }],
  spend_status: 'locked_disarmed',
};

describe('normalizeIbkrStatus (QA C1 / C4)', () => {
  it('returns a well-formed payload value-for-value', () => {
    expect(normalizeIbkrStatus(GOOD)).toEqual(GOOD);
  });

  it('turns recording lists sent as one object into lists (C1)', () => {
    const out = normalizeIbkrStatus({
      ...GOOD,
      capture_stopped: { symbol: 'GRML', at: 1, reason: 'failure', resumed: false },
      capture_resume: { GRML: { attempt: 1 } },
      capture_sessions: { GDC: { counts: {} } },
    });
    expect(out?.capture_stopped).toEqual([]);
    expect(out?.capture_resume).toEqual([]);
    expect(out?.capture_sessions).toEqual([]);
  });

  it('keeps only rows that name a symbol', () => {
    const out = normalizeIbkrStatus({ ...GOOD, capture_sessions: [null, 'GDC', { counts: {} }, { symbol: 'GDC' }] });
    expect(out?.capture_sessions).toEqual([{ symbol: 'GDC' }]);
  });

  it('never hands a non-string account id or a non-list id list to the pill (C4)', () => {
    const out = normalizeIbkrStatus({ ...GOOD, account_id: 7654321, account_ids: 'U7654321' });
    expect(out?.account_id).toBeNull();
    expect(out?.account_ids).toEqual([]);
    expect(normalizeIbkrStatus({ ...GOOD, capture_symbols: 'GDC' })?.capture_symbols).toEqual([]);
  });

  it('leaves absent fields absent and drops invalid venue / mode values', () => {
    const out = normalizeIbkrStatus({ connected: 'yes', mode: 'demo', venue: 'moon', spend_status: 5 });
    expect(out).toEqual({ connected: false, mode: 'disconnected' });
  });

  it('refuses a body that is not an object at all', () => {
    for (const body of [null, [], 'ok', 3]) expect(normalizeIbkrStatus(body)).toBeNull();
  });
});
