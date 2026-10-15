import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LossLimitAccount, LossLimitView } from './lossLimitApi';
import { lossLimitCloseLine, noteLossLimit, resetLossLimitNoticesForTests } from './lossLimitNotices';

/** 2026-10-15 10:12 ET. */
const AT_1012 = Date.UTC(2026, 9, 15, 14, 12) / 1000;

function account(over: Partial<LossLimitAccount> = {}): LossLimitAccount {
  return {
    name: 'Paper', counted_at: AT_1012, pnl: -100, loss: 100, unknown: null,
    warned_at: null, warned_loss: null, tripped_at: null, tripped_loss: null, limit_usd: null,
    sold: null, sell_error: null, no_new_buys: null,
    ...over,
  };
}

function view(accounts: LossLimitView['accounts']): LossLimitView {
  return {
    schema_version: 1,
    settings: { limit_usd: 2000, warn: true, no_new_buys: true, auto_sell: true, set_at: null, source: 'operator', error: null },
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

  it('writes a close without an order id or a quantity plainly', () => {
    expect(lossLimitCloseLine({ symbol: 'SOFI', side: 'SELL', qty: 100, ok: true, order_id: null, error: null }))
      .toBe('Sold 100 SOFI');
    expect(lossLimitCloseLine({ symbol: 'SOFI', side: 'SELL', qty: Number.NaN, ok: false, order_id: null, error: null }))
      .toBe('SOFI was not sold — the close was refused');
  });
});
