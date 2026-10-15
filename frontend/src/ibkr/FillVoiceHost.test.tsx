/**
 * @vitest-environment jsdom
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrAccountPollSnap } from './ibkrAccountPoller';
import type { IbkrOrder, IbkrPosition } from './types';

const poller = vi.hoisted(() => ({
  snap: null as unknown as IbkrAccountPollSnap,
  listeners: new Set<() => void>(),
  leader: true,
  refreshOrders: vi.fn(),
}));
const speakDesk = vi.hoisted(() => vi.fn());

vi.mock('./ibkrAccountPoller', () => ({
  getIbkrAccountSnapshot: () => poller.snap,
  isIbkrAccountPollLeader: () => poller.leader,
  refreshIbkrOrdersNow: poller.refreshOrders,
  subscribeIbkrAccount: (fn: () => void) => {
    poller.listeners.add(fn);
    return () => poller.listeners.delete(fn);
  },
}));
vi.mock('../sound', () => ({ speakDesk }));

import { FillVoiceHost } from './FillVoiceHost';

function row(filled: number): IbkrOrder {
  return {
    order_id: 3, symbol: 'MNDR', side: 'BUY', qty: 500, filled_qty: filled,
    order_type: 'MKT', limit_price: null, status: filled >= 500 ? 'Filled' : 'Submitted',
  };
}

function position(qty: number): IbkrPosition {
  return {
    symbol: 'MNDR', qty, market_price: null, market_value: null, avg_cost: null,
    unrealized_pnl: null, realized_pnl: null,
  };
}

function publish(over: Partial<IbkrAccountPollSnap>) {
  poller.snap = { ...poller.snap, ...over };
  act(() => poller.listeners.forEach(fn => fn()));
}

beforeEach(() => {
  poller.snap = {
    summary: null, positions: [], orders: [], closedOrders: [], loading: false, error: null,
    stale: false, staleSince: null, venue: 'paper', ordersRead: true,
  };
  poller.listeners.clear();
  poller.leader = true;
  poller.refreshOrders.mockClear();
  speakDesk.mockClear();
});

afterEach(cleanup);

describe('FillVoiceHost', () => {
  it('says a fill that arrives after the desk read its rows, once', () => {
    render(<FillVoiceHost />);
    publish({ closedOrders: [row(500)] });
    publish({ closedOrders: [row(500)] });
    expect(speakDesk.mock.calls).toEqual([['Bought 500 shares of M N D R.']]);
  });

  it('a window that does not poll the account stays silent', () => {
    poller.leader = false;
    render(<FillVoiceHost />);
    publish({ closedOrders: [row(500)] });
    expect(speakDesk).not.toHaveBeenCalled();
  });

  it('reads the order rows at once when a position moves', () => {
    render(<FillVoiceHost />);
    expect(poller.refreshOrders).not.toHaveBeenCalled();
    publish({ positions: [position(500)] });
    expect(poller.refreshOrders).toHaveBeenCalledTimes(1);
    publish({ positions: [position(500)] });
    expect(poller.refreshOrders).toHaveBeenCalledTimes(1);
  });

  it('a venue change is no fill and asks for nothing', () => {
    poller.snap = { ...poller.snap, closedOrders: [row(500)] };
    render(<FillVoiceHost />);
    publish({ venue: 'live', positions: [position(100)], closedOrders: [row(500)] });
    expect(poller.refreshOrders).not.toHaveBeenCalled();
    expect(speakDesk).not.toHaveBeenCalled();
  });
});
