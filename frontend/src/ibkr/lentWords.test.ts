import { describe, expect, it } from 'vitest';
import { depthLentText, lentFromFrame, lentFromLoan, tapeLentText } from './lentWords';

describe('depthLentText (ADR 044 decision 6)', () => {
  it("names the setup that took the line and why, and when it comes back", () => {
    expect(depthLentText({ symbol: 'AISP', setupType: 'first_pullback', tier: 'near', why: 'near its trigger' })).toBe(
      "Level 2 lent to AISP's first pullback (near its trigger) — back when it ends or when you bring this tab to the front",
    );
  });

  it("says a trade and the other setups in the desk's words", () => {
    expect(depthLentText({ symbol: 'IPDN', setupType: 'flat_top_breakout', tier: 'trade', why: null })).toBe(
      "Level 2 lent to IPDN's flat-top breakout (in a trade) — back when it ends or when you bring this tab to the front",
    );
  });

  it("takes the backend's words for a reason the desk does not know", () => {
    expect(depthLentText({ symbol: 'AISP', setupType: 'some_new_setup', tier: null, why: 'waiting' })).toContain(
      "AISP's some new setup (waiting)",
    );
  });

  it('a frame that names no borrower still says the line is lent and when it comes back', () => {
    expect(depthLentText({ symbol: null, setupType: null, tier: null, why: null })).toBe(
      "Level 2 lent to one of Nova's setups — back when it ends or when you bring this tab to the front",
    );
  });
});

describe('tapeLentText', () => {
  it('says the Time & Sales line went with the book, in the same words', () => {
    expect(tapeLentText({ symbol: 'AISP', setupType: 'first_pullback', tier: 'armed', why: 'armed' })).toBe(
      "Time & Sales lent to AISP's first pullback (armed) — back when it ends or when you bring this tab to the front",
    );
  });
});

describe('the lent fields', () => {
  it('reads a lent frame, and states nothing a broken one does not carry', () => {
    expect(lentFromFrame({
      type: 'lent', symbol: 'ABC', to: { symbol: 'aisp', setup_type: 'bull_flag', setup_id: 'AISP-1' },
      why: 'in a trade', tier: 'trade', since: 1_790_900_000, text: 'Level 2 lent to ...',
    })).toEqual({
      symbol: 'AISP', setupType: 'bull_flag', tier: 'trade', why: 'in a trade', since: 1_790_900_000,
      text: 'Level 2 lent to ...',
    });
    expect(lentFromFrame({ type: 'lent', to: 'AISP', since: 'soon' })).toEqual({
      symbol: null, setupType: null, tier: null, why: null, since: null, text: null,
    });
  });

  it("takes the poll's newest reason for a standing loan", () => {
    expect(lentFromLoan({
      lender: 'ABC', borrower: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-1', since: 5,
      why: 'near its trigger', tier: 'near', text: null, tape: false, tape_state: 'waiting', tape_error: null,
      tape_lent: true, tape_last_print: null,
    })).toEqual({
      symbol: 'AISP', setupType: 'first_pullback', tier: 'near', why: 'near its trigger', since: 5, text: null,
    });
  });
});
