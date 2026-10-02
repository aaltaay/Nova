/**
 * GET /api/ibkr/depth/lines as the desk reads it (ADR 043 decision 6): who holds each line, the
 * loans, and what a lent tab's poll reads.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { loanFor, normalizeDepthLines, readLines } from './depthLines';

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
      tape_state: 'receiving', tape_error: null, tape_lent: true, tape_last_print: 1_790_904_661.0,
      text: 'Level 2 lent to ...',
    }, {
      lender: 'GHI', borrower: 'MSGY', setup_type: 'bull_flag', setup_id: null, since: 1.0, why: 'armed',
      tier: 'armed', state: 'active', tape: false, tape_state: 'refused',
      tape_error: 'Max number of tick-by-tick requests has been reached.', tape_lent: false, tape_last_print: null,
    }],
    recent: [{
      lender: 'XYZ', borrower: 'MSGY', setup_type: 'bull_flag', since: 1.0, ended: 2.0, end: 'recalled',
      tape_lent: true,
    }],
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
    expect(view.lending.recent[0]).toMatchObject({ lender: 'XYZ', end: 'recalled', ended: 2, tape_lent: true });
  });

  it("says whether each setup's own Time & Sales line is up, and why not", () => {
    const [up, refused] = normalizeDepthLines(VIEW)!.lending.loans;
    expect(up).toMatchObject({ tape: true, tape_state: 'receiving', tape_error: null, tape_lent: true,
      tape_last_print: 1_790_904_661 });
    expect(refused).toMatchObject({ tape: false, tape_state: 'refused', tape_lent: false,
      tape_error: 'Max number of tick-by-tick requests has been reached.' });
  });

  it('an older backend says nothing about the tape: every tape field is null, never false', () => {
    const old = { ...VIEW, lending: { ...VIEW.lending, loans: [{ lender: 'ABC', borrower: 'AISP' }] } };
    expect(normalizeDepthLines(old)!.lending.loans[0]).toMatchObject({
      tape: null, tape_state: null, tape_error: null, tape_lent: null, tape_last_print: null });
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

describe('readLines', () => {
  afterEach(() => vi.unstubAllGlobals());

  function answer(status: number, body: unknown) {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: status < 400, status, json: async () => body })));
  }

  it('reads the view', async () => {
    answer(200, VIEW);
    const got = await readLines();
    expect(got.kind).toBe('view');
    if (got.kind === 'view') expect(loanFor(got.view, 'ABC')?.borrower).toBe('AISP');
  });

  it('a backend without the route lends nothing; one that fails is unknown, and says why', async () => {
    answer(404, { detail: 'Not Found' });
    expect((await readLines()).kind).toBe('none');
    answer(503, { detail: 'down' });
    expect(await readLines()).toEqual({ kind: 'unknown', error: 'GET /api/ibkr/depth/lines answered 503' });
    answer(200, { detail: 'not the view' });
    expect((await readLines()).kind).toBe('unknown');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    expect(await readLines()).toEqual({ kind: 'unknown', error: 'Failed to fetch' });
  });
});
