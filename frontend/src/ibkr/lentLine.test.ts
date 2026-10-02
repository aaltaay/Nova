/**
 * @vitest-environment jsdom
 *
 * The lent pane's state (ADR 043 decision 6): it never reconnects by its backoff while lent, asks
 * again when the loan ends or at once from the front, and keeps its words until its line answers.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { L2_LENT_POLL_MS } from '../constantGroups/market_ui';
import { LentLine } from './lentLine';
import { loanWatchersForTests, resetLoanWatchForTests } from './loanWatch';

const FRAME = {
  type: 'lent', symbol: 'ABC', to: { symbol: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-1' },
  why: 'armed', tier: 'armed', since: 1, text: 'Level 2 lent to ...',
};

function lines(loans: unknown[]) {
  return {
    ok: true, status: 200,
    json: async () => ({ schema_version: 1, cap: 3, lines: [], lending: { on: true, loans, recent: [], error: null } }),
  };
}

describe('LentLine', () => {
  let front: boolean;
  let reconnect: ReturnType<typeof vi.fn>;
  let changed: ReturnType<typeof vi.fn>;
  let fetchMock: ReturnType<typeof vi.fn>;
  let line: LentLine;

  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    front = false;
    reconnect = vi.fn();
    changed = vi.fn();
    line = new LentLine('abc', { inFront: () => front, reconnect, changed });
  });

  afterEach(() => {
    line.dispose();
    resetLoanWatchForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('a line that was never lent leaves the close to the backoff', () => {
    expect(line.closed()).toBe(false);
    expect(loanWatchersForTests()).toBe(0);
  });

  it('a hidden pane waits on the poll, takes the newest reason, and asks again when the loan ends', async () => {
    line.lend(FRAME);
    expect(line.lent).toMatchObject({ symbol: 'AISP', tier: 'armed' });
    expect(line.closed()).toBe(true);
    expect(reconnect).not.toHaveBeenCalled();
    expect(loanWatchersForTests()).toBe(1);
    fetchMock.mockResolvedValueOnce(lines([{ lender: 'ABC', borrower: 'AISP', tier: 'near', why: 'near its trigger' }]));
    await vi.advanceTimersByTimeAsync(L2_LENT_POLL_MS);
    expect(line.lent).toMatchObject({ tier: 'near' });
    expect(changed).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValueOnce(lines([]));
    await vi.advanceTimersByTimeAsync(L2_LENT_POLL_MS);
    expect(reconnect).toHaveBeenCalledTimes(1);
    expect(loanWatchersForTests()).toBe(0);
    expect(line.lent).not.toBeNull();                      // the words stay until the line answers
    line.answered();
    expect(line.lent).toBeNull();
  });

  it('a pane in front asks for its line back at once', () => {
    front = true;
    line.lend(FRAME);
    expect(line.closed()).toBe(true);
    expect(reconnect).toHaveBeenCalledTimes(1);
    expect(loanWatchersForTests()).toBe(0);
  });

  it('a hidden pane brought to the front asks at once, only once', () => {
    line.lend(FRAME);
    line.closed();
    line.wake();
    expect(reconnect).not.toHaveBeenCalled();             // still hidden
    front = true;
    line.wake();
    line.wake();
    expect(reconnect).toHaveBeenCalledTimes(1);
    expect(loanWatchersForTests()).toBe(0);
  });

  it('a take-back that closes unanswered hands over to the backoff', () => {
    front = true;
    line.lend(FRAME);
    line.closed();
    expect(line.closed()).toBe(false);
    expect(line.lent).toBeNull();
  });

  it('the document coming back into view wakes it', () => {
    line.lend(FRAME);
    line.closed();
    front = true;
    document.dispatchEvent(new Event('visibilitychange'));
    expect(reconnect).toHaveBeenCalledTimes(1);
  });
});
