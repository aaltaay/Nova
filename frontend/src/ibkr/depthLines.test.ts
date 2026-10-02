/**
 * GET /api/ibkr/depth/lines as the desk reads it (ADR 043 decision 6): who holds each line, the
 * loans, and what a lent tab's poll concludes.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { loanFor, normalizeDepthLines, pollLoan } from './depthLines';

const VIEW = {
  schema_version: 1,
  generated_at: 1_790_904_661.5,
  cap: 3,
  lines: [
    { symbol: 'AISP', held_by: 'loan', front: false, viewers: 1 },
    { symbol: 'DEF', held_by: 'tab', front: true, viewers: 1 },
    { symbol: 'GHI', held_by: 'tab', front: null, viewers: 2 },
    { symbol: 'BAD', held_by: 'nobody', front: true, viewers: 1 },
  ],
  lending: {
    on: true,
    loans: [{
      lender: 'ABC', borrower: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-2026-10-01-1',
      since: 1_790_904_660.0, why: 'near its trigger', tier: 'near', state: 'active', tape: true,
      tape_error: null, text: 'Level 2 lent to ...',
    }],
    recent: [{ lender: 'XYZ', borrower: 'MSGY', setup_type: 'bull_flag', since: 1.0, ended: 2.0, end: 'recalled' }],
    error: null,
  },
};

describe('normalizeDepthLines', () => {
  it('keeps the lines and loans as sent, and drops a holder it does not know', () => {
    const view = normalizeDepthLines(VIEW)!;
    expect(view.cap).toBe(3);
    expect(view.lines.map((l) => [l.symbol, l.held_by, l.front, l.viewers])).toEqual([
      ['AISP', 'loan', false, 1], ['DEF', 'tab', true, 1], ['GHI', 'tab', null, 2]]);
    expect(view.lending.on).toBe(true);
    expect(view.lending.loans[0]).toMatchObject({ lender: 'ABC', borrower: 'AISP', why: 'near its trigger', tier: 'near' });
    expect(view.lending.recent[0]).toMatchObject({ lender: 'XYZ', end: 'recalled', ended: 2 });
  });

  it('is null for an answer that is not the view', () => {
    expect(normalizeDepthLines(null)).toBeNull();
    expect(normalizeDepthLines({ detail: 'Not Found' })).toBeNull();
  });

  it('finds the loan that took a symbol, whatever its case', () => {
    const view = normalizeDepthLines(VIEW)!;
    expect(loanFor(view, 'abc')?.borrower).toBe('AISP');
    expect(loanFor(view, 'DEF')).toBeNull();
  });
});

describe('pollLoan', () => {
  afterEach(() => vi.unstubAllGlobals());

  function answer(status: number, body: unknown) {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: status < 400, status, json: async () => body })));
  }

  it('says the loan stands while one names the symbol, and ended once none does', async () => {
    answer(200, VIEW);
    expect((await pollLoan('ABC')).kind).toBe('standing');
    answer(200, { ...VIEW, lending: { ...VIEW.lending, loans: [] } });
    expect((await pollLoan('ABC')).kind).toBe('ended');
  });

  it('a backend without the route lends nothing; one that fails is unknown', async () => {
    answer(404, { detail: 'Not Found' });
    expect((await pollLoan('ABC')).kind).toBe('ended');
    answer(503, { detail: 'down' });
    expect((await pollLoan('ABC')).kind).toBe('unknown');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    expect((await pollLoan('ABC')).kind).toBe('unknown');
  });
});
