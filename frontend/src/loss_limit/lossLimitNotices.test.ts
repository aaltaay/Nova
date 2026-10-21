import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LossLimitAccount, LossLimitLine, LossLimitLineId, LossLimitView } from './lossLimitApi';
import { lossLimitCloseLine, noteLossLimit, resetLossLimitNoticesForTests } from './lossLimitNotices';

/** 2026-10-15 10:12 ET. */
const AT_1012 = Date.UTC(2026, 9, 15, 14, 12) / 1000;

type LineOver = Partial<LossLimitLine> & { name?: string };

function line(over: Partial<LossLimitLine> = {}): LossLimitLine {
  return {
    on: true, pnl: -100, loss: 100, warned_at: null, warned_loss: null, tripped_at: null, tripped_loss: null,
    limit_usd: null, sold: null, sell_error: null, no_new_buys: null,
    ...over,
  };
}

/** An account whose Account line is `over` (ADR 056's one line); `lines` sets the You and Bots lines. */
function account(over: LineOver = {}, lines: Partial<Record<LossLimitLineId, Partial<LossLimitLine>>> = {}): LossLimitAccount {
  const { name, ...rec } = over;
  return {
    name: name ?? 'Paper', counted_at: AT_1012, pnl: -100, loss: 100, unknown: null,
    lines: {
      account: line(rec),
      you: line({ on: false, ...lines.you }),
      bots: line({ on: false, ...lines.bots }),
    },
  };
}

function view(accounts: LossLimitView['accounts']): LossLimitView {
  return {
    schema_version: 2,
    settings: { limit_usd: 2000, you_usd: 300, bots_usd: 500, warn: true, no_new_buys: true, auto_sell: true,
      set_at: null, source: 'operator', error: null },
    day: '2026-10-15', until: AT_1012 + 18 * 3600, accounts, error: null,
  };
}

const NO_NEW_BUYS = 'Daily loss limit reached on Paper at 10:12 ET (down $2,040.00 against your $2,000 limit): no new buys '
  + 'until 04:00 ET Fri Oct 16.';

describe('the daily loss limit\'s notices (ADR 056)', () => {
  beforeEach(() => resetLossLimitNoticesForTests());

  it('raises a warning once, and says it', () => {
    const push = vi.fn();
    const speak = vi.fn();
    const v = view({ paper: account({ warned_at: AT_1012, warned_loss: 1620.4 }) });
    expect(noteLossLimit(v, push, speak, AT_1012 + 5)).toBe(1);
    expect(push).toHaveBeenCalledWith({
      tone: 'warn', title: 'Loss limit: 80% reached', text: 'Paper is down $1,620 of your $2,000 daily loss limit.',
    });
    expect(speak).toHaveBeenCalledWith('Loss limit warning. Paper is down 1,620 dollars of 2,000.');
    // The next read of the same answer is not news.
    expect(noteLossLimit(v, push, speak, AT_1012 + 8)).toBe(0);
    expect(push).toHaveBeenCalledTimes(1);
    expect(speak).toHaveBeenCalledTimes(1);
  });

  it('raises a trip with what holds now and every sale, once, and the trip replaces the warning', () => {
    const push = vi.fn();
    const speak = vi.fn();
    const v = view({
      paper: account({
        warned_at: AT_1012 - 60, warned_loss: 1650,
        tripped_at: AT_1012, tripped_loss: 2040, limit_usd: 2000,
        sold: [
          { symbol: 'weto', side: 'SELL', qty: 1000, ok: true, order_id: 259, error: null },
          { symbol: 'AMC', side: 'BUY', qty: 50, ok: true, order_id: 260, error: null },
          { symbol: 'GME', side: 'SELL', qty: 20, ok: false, order_id: null, error: 'IBKR refused the close' },
        ],
        no_new_buys: { text: NO_NEW_BUYS, until: AT_1012 + 18 * 3600 },
      }),
    });
    expect(noteLossLimit(v, push, speak, AT_1012 + 3)).toBe(1);
    expect(push).toHaveBeenCalledTimes(1);
    expect(push.mock.calls[0][0]).toEqual({
      tone: 'bad',
      title: 'Daily loss limit reached',
      text: [
        'Paper is down $2,040 against your $2,000 limit · 10:12 ET',
        NO_NEW_BUYS,
        'Sold 1,000 WETO · order 259',
        'Bought back 50 AMC · order 260',
        '20 GME was not sold — IBKR refused the close',
      ].join('\n'),
    });
    expect(speak).toHaveBeenCalledWith('Daily loss limit reached on Paper.');
    expect(noteLossLimit(v, push, speak, AT_1012 + 6)).toBe(0);
    expect(push).toHaveBeenCalledTimes(1);
  });

  it('waits for Auto sell to answer, then says what was sold (PR #1003 review)', () => {
    const push = vi.fn();
    const trip = { tripped_at: AT_1012, tripped_loss: 2040, limit_usd: 2000 };
    const selling = view({ paper: account({ ...trip, sell: 'pending' }) });
    expect(noteLossLimit(selling, push, null, AT_1012 + 2)).toBe(0);             // still selling: not seen yet
    const done = view({ paper: account({ ...trip, sell: 'done',
      sold: [{ symbol: 'WETO', side: 'SELL', qty: 10000, ok: true, order_id: 259, error: null }] }) });
    expect(noteLossLimit(done, push, null, AT_1012 + 5)).toBe(1);
    expect(push.mock.calls[0][0].text).toContain('Sold 10,000 WETO · order 259');
    expect(noteLossLimit(done, push, null, AT_1012 + 8)).toBe(0);                 // once
  });

  it('says a trip whose Auto sell is slow after 30 s, and that it is still selling', () => {
    const push = vi.fn();
    const slow = view({ paper: account({ tripped_at: AT_1012, tripped_loss: 2040, limit_usd: 2000, sell: 'pending' }) });
    expect(noteLossLimit(slow, push, null, AT_1012 + 29)).toBe(0);
    expect(noteLossLimit(slow, push, null, AT_1012 + 31)).toBe(1);
    expect(push.mock.calls[0][0].text).toContain('Auto sell is still selling');
  });

  it('says why nothing was sold when the sale could not start', () => {
    const push = vi.fn();
    const v = view({ live: account({ name: 'Live', tripped_at: AT_1012, tripped_loss: 2010, limit_usd: 2000,
      sold: [], sell_error: 'IBKR is not connected' }) });
    noteLossLimit(v, push, null, AT_1012 + 1);
    expect(push.mock.calls[0][0].text).toBe('Live is down $2,010 against your $2,000 limit · 10:12 ET\nIBKR is not connected');
  });

  it('never announces an old warning or trip, and never speaks in a window that only follows', () => {
    const push = vi.fn();
    const old = view({ paper: account({ tripped_at: AT_1012, tripped_loss: 2040, limit_usd: 2000 }) });
    expect(noteLossLimit(old, push, null, AT_1012 + 601)).toBe(0);
    expect(push).not.toHaveBeenCalled();
    const fresh = view({ sim: account({ name: 'Sim', warned_at: AT_1012, warned_loss: 1600 }) });
    expect(noteLossLimit(fresh, push, null, AT_1012 + 1)).toBe(1);
    expect(push.mock.calls[0][0].text).toBe('Sim is down $1,600 of your $2,000 daily loss limit.');
  });

  it('a limit changed and crossed again is news again', () => {
    const push = vi.fn();
    noteLossLimit(view({ paper: account({ warned_at: AT_1012, warned_loss: 1600 }) }), push, null, AT_1012 + 1);
    noteLossLimit(view({ paper: account({ warned_at: AT_1012 + 120, warned_loss: 1610 }) }), push, null, AT_1012 + 121);
    expect(push).toHaveBeenCalledTimes(2);
  });

  it('names the bots\' line in its notice and voice, and says only the bots stopped (ADR 061)', () => {
    const push = vi.fn();
    const speak = vi.fn();
    const stop = 'The bots\' daily loss limit reached on Paper at 10:12 ET (the bots\' trades down $510 against their '
      + '$500 limit): no new bot entries until 04:00 ET Fri Oct 16; your own buys still work.';
    const v = view({ paper: account({}, { bots: {
      on: true, tripped_at: AT_1012, tripped_loss: 510, limit_usd: 500, sell: 'done',
      sold: [{ symbol: 'X', side: 'SELL', qty: 100, ok: true, order_id: 261, error: null }],
      no_new_buys: { line: 'bots', text: stop, until: AT_1012 + 18 * 3600 },
    } }) });
    expect(noteLossLimit(v, push, speak, AT_1012 + 2)).toBe(1);
    expect(push.mock.calls[0][0]).toEqual({
      tone: 'bad',
      title: 'The bots\' loss limit reached',
      text: ['The bots\' trades on Paper are down $510 against their $500 limit · 10:12 ET', stop,
        'Sold 100 X · order 261'].join('\n'),
    });
    expect(speak).toHaveBeenCalledWith('The bots\' loss limit reached on Paper.');
  });

  it('warns on your trades\' line with its own limit, and the account line\'s trip does not hide it', () => {
    const push = vi.fn();
    const speak = vi.fn();
    const v = view({ paper: account({ tripped_at: AT_1012 + 30, tripped_loss: 2040, limit_usd: 2000 },
      { you: { on: true, warned_at: AT_1012, warned_loss: 250, limit_usd: 300 } }) });
    expect(noteLossLimit(v, push, speak, AT_1012 + 31)).toBe(2);
    expect(push.mock.calls[0][0]).toEqual({
      tone: 'warn', title: 'Your trades\' loss limit: 80% reached',
      text: 'Your trades on Paper are down $250 of your $300 limit.',
    });
    expect(speak.mock.calls[0][0]).toBe('Loss limit warning. Your trades on Paper are down 250 dollars of 300.');
    expect(push.mock.calls[1][0].title).toBe('Daily loss limit reached');
  });

  it('writes a close without an order id or a quantity plainly', () => {
    expect(lossLimitCloseLine({ symbol: 'SOFI', side: 'SELL', qty: 100, ok: true, order_id: null, error: null }))
      .toBe('Sold 100 SOFI');
    expect(lossLimitCloseLine({ symbol: 'SOFI', side: 'SELL', qty: Number.NaN, ok: false, order_id: null, error: null }))
      .toBe('SOFI was not sold — the close was refused');
  });
});
