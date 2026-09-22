import { describe, expect, it, vi } from 'vitest';
import { fetchOrdersCluster, fetchAccountCluster } from './ibkrAccountFetch';
import { normalizeOrderList, normalizeOrderRow, normalizePositionList } from './orderRowNormalize';

const ROW = {
  order_id: 7,
  perm_id: 4001,
  symbol: 'GRML',
  side: 'BUY',
  qty: 100,
  filled_qty: 100,
  order_type: 'LMT',
  limit_price: 8.86,
  status: 'Filled',
  submitted_at: '2026-09-21T21:05:53.000Z',
  filled_at: '2026-09-21T21:05:54.000Z',
};

describe('order rows are shaped once, where they are fetched (QA C2 / C3)', () => {
  it('a well-formed row comes back value-for-value', () => {
    expect(normalizeOrderRow(ROW)).toEqual(ROW);
  });

  it('null text fields become strings and a numeric timestamp becomes null (C2)', () => {
    const out = normalizeOrderRow({ ...ROW, status: null, side: null, order_type: null, submitted_at: 1_790_000_000 });
    expect(out).toMatchObject({ status: '', side: '', order_type: '', submitted_at: null });
  });

  it('numbers are finite or null', () => {
    const out = normalizeOrderRow({ ...ROW, qty: '100', limit_price: 'n/a', avg_fill_price: Infinity });
    expect(out).toMatchObject({ qty: 100, limit_price: null, avg_fill_price: null });
  });

  it('a list that is not a list is refused, rows that are not objects are dropped (C3)', () => {
    expect(normalizeOrderList({})).toBeNull();
    expect(normalizeOrderList([null, ROW, 'x'])).toEqual([ROW]);
    expect(normalizePositionList({})).toBeNull();
    expect(normalizePositionList([{ qty: 1 }, { symbol: 'SPCX', qty: '2' }])).toEqual([{ symbol: 'SPCX', qty: 2 }]);
  });

  it('the account poller names the failure instead of handing on an object', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) })));
    const orders = await fetchOrdersCluster('http://test');
    expect(orders.orders).toBeNull();
    expect(orders.failures).toEqual(['orders (unexpected shape)', 'closed orders (unexpected shape)']);
    const account = await fetchAccountCluster('http://test');
    expect(account.positions).toBeNull();
    expect(account.failures).toEqual(['positions (unexpected shape)']);
    vi.unstubAllGlobals();
  });

  it('an unreadable body is a named failure too', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('html'); } })));
    const orders = await fetchOrdersCluster('http://test');
    expect(orders.failures).toEqual(['orders (unreadable response)', 'closed orders (unreadable response)']);
    vi.unstubAllGlobals();
  });
});
