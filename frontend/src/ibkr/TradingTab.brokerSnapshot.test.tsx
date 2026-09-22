/**
 * QA D20 (2026-09-22): the Account page's Broker snapshot (TradingTab without
 * its ticket) was one 240 px column on a ~1,200 px page -- the account column
 * sat in the first track of a three-track grid built for book + ticket + account.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TradingTab } from './TradingTab';

vi.mock('./useIbkrStatus', () => ({ useIbkrStatus: () => ({ connected: true, mode: 'live', spend_status: 'locked' }) }));
vi.mock('./useIbkrAccount', () => ({
  useIbkrAccount: () => ({ summary: null, positions: [], orders: [], error: null, refresh: () => {} }),
}));
vi.mock('../workspace', () => ({ useModuleVisibility: () => ({ isVisible: () => false }) }));
vi.mock('../hotkeys/TopOfBookContext', () => ({ useTopOfBook: () => ({ topOfBook: null }) }));
vi.mock('./PositionsPanel', () => ({ PositionsPanel: () => <div data-testid="positions-panel" /> }));
vi.mock('./DepthLadder', () => ({ DepthLadder: () => <div data-testid="depth-ladder" /> }));
vi.mock('./OrderTicket', () => ({ OrderTicket: () => <div data-testid="order-ticket" /> }));
vi.mock('./PaperTradingBanner', () => ({ PaperTradingBanner: () => null }));
vi.mock('../closed_orders', () => ({ ClosedOrdersModule: () => null }));

describe('TradingTab layout', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  it('hosted without the ticket, the account column takes the whole row', () => {
    act(() => root.render(<TradingTab selectedSymbol={null} onSelectSymbol={() => {}} onOpenTrading={() => {}} showTicket={false} sections={['overview']} />));
    const layout = mount.querySelector('.ibkr-trading-layout');
    expect(layout?.classList.contains('ibkr-trading-layout--account-only')).toBe(true);
    expect(mount.querySelector('[data-testid="order-ticket"]')).toBeNull();
  });

  it('with the ticket it keeps the three tracks', () => {
    act(() => root.render(<TradingTab selectedSymbol={null} onSelectSymbol={() => {}} onOpenTrading={() => {}} sections={['overview']} />));
    const layout = mount.querySelector('.ibkr-trading-layout');
    expect(layout?.classList.contains('ibkr-trading-layout--account-only')).toBe(false);
    expect(mount.querySelector('[data-testid="order-ticket"]')).toBeTruthy();
  });
});
