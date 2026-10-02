/**
 * The one lines poll every lent pane in a window waits on (ADR 044 decision 6): one request per
 * L2_LENT_POLL_MS answers every pane, an unreadable answer ends nothing, and the poll stops when no
 * pane waits.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { L2_LENT_POLL_MS } from '../constantGroups/market_ui';
import type { DepthLoan } from './depthLines';
import { loanWatchersForTests, resetLoanWatchForTests, watchLoan, type LoanWatcher } from './loanWatch';

const LOAN = {
  lender: 'ABC', borrower: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-1', since: 1, why: 'near its trigger',
  tier: 'near', text: null, tape: false, tape_state: 'waiting', tape_error: null, tape_lent: true, tape_last_print: null,
};

function answer(loans: unknown[]) {
  return {
    ok: true, status: 200,
    json: async () => ({ schema_version: 1, cap: 3, lines: [], lending: { on: true, loans, recent: [], error: null } }),
  };
}

function watcher() {
  const heard: Array<DepthLoan | 'ended'> = [];
  const w: LoanWatcher = { standing: (loan) => heard.push(loan), ended: () => heard.push('ended') };
  return { w, heard };
}

describe('watchLoan', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  async function wait(ms: number) {
    await vi.advanceTimersByTimeAsync(ms);
  }

  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    resetLoanWatchForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("answers a tab's Level 2 and Time & Sales from one request", async () => {
    const depth = watcher();
    const tape = watcher();
    const other = watcher();
    watchLoan('ABC', depth.w);
    watchLoan('abc', tape.w);
    watchLoan('GHI', other.w);
    fetchMock.mockResolvedValue(answer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/ibkr/depth/lines');
    expect(depth.heard).toEqual([expect.objectContaining({ lender: 'ABC', borrower: 'AISP', tier: 'near' })]);
    expect(tape.heard).toEqual(depth.heard);
    expect(other.heard).toEqual(['ended']);                // no loan names GHI
  });

  it('a pane that stops waiting is not told again, and the poll stops with the last one', async () => {
    const depth = watcher();
    const stopDepth = watchLoan('ABC', depth.w);
    const stopTape = watchLoan('ABC', watcher().w);
    fetchMock.mockResolvedValue(answer([LOAN]));
    stopDepth();
    await wait(L2_LENT_POLL_MS);
    expect(depth.heard).toEqual([]);
    expect(loanWatchersForTests()).toBe(1);
    stopTape();
    await wait(5 * L2_LENT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(1);           // nobody waits: no request
  });

  it('an answer that cannot be read ends nothing, and is logged once per run of failures', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const depth = watcher();
    watchLoan('ABC', depth.w);
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await wait(3 * L2_LENT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(depth.heard).toEqual([]);                       // still lent
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('Failed to fetch');
    fetchMock.mockResolvedValue(answer([]));
    await wait(L2_LENT_POLL_MS);
    expect(depth.heard).toEqual(['ended']);
  });

  it('a backend without the route lends nothing: every pane takes its line back', async () => {
    const depth = watcher();
    watchLoan('ABC', depth.w);
    fetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: 'Not Found' }) });
    await wait(L2_LENT_POLL_MS);
    expect(depth.heard).toEqual(['ended']);
  });

  it("one pane's trouble never keeps the others from the answer", async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const tape = watcher();
    watchLoan('ABC', { standing: () => { throw new Error('boom'); }, ended: () => {} });
    watchLoan('ABC', tape.w);
    fetchMock.mockResolvedValue(answer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    expect(tape.heard).toHaveLength(1);
    expect(warn).toHaveBeenCalledTimes(1);
  });
});
