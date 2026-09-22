/**
 * QA R32 remainder (2026-09-22): the rail's Flatten wrote "Flatten order #N"
 * (or its refusal) into this bar's footer, which the Trader rail hides, so the
 * operator saw no outcome while the ticket's Last line still named the previous
 * order. The outcome now lands on the ticket's Last line.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TopOfBookProvider } from '../hotkeys/TopOfBookContext';
import { TickerTradeActionBar } from './TickerTradeActionBar';
import type { IbkrAccountSummary, IbkrPosition } from './types';

const mocks = vi.hoisted(() => ({ close: vi.fn(), notify: vi.fn() }));

vi.mock('../ux', () => ({ confirmApp: async () => true, alertApp: async () => undefined }));
vi.mock('./useTradingPinGate', () => ({ useTradingPinGate: () => ({ ensureUnlocked: async () => true, pinDialog: null }) }));
vi.mock('./closeFullPosition', () => ({ closeFullPosition: (...args: unknown[]) => mocks.close(...args) }));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: (...args: unknown[]) => mocks.notify(...args) }));
vi.mock('../hotkeys/NovaActionRuntimeSync', () => ({ NovaActionRuntimeSync: () => null }));
vi.mock('../hotkeys/TradingQuickBar', () => ({ TradingQuickBar: () => null }));
vi.mock('./TickerTradeAutomateControls', () => ({ TickerTradeAutomateControls: () => null }));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
  tryUnlockTicketSession: () => true,
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, mode: 'paper', spend_status: 'paper_armed', short_enabled: false }),
}));

const SUMMARY = { connected: true, NetLiquidation: 100_000, BuyingPower: 400_000 } as IbkrAccountSummary;
const POSITION: IbkrPosition = {
  symbol: 'GRML', qty: 2, market_price: 9.3, market_value: 18.6, avg_cost: 9.2, unrealized_pnl: 0.2, realized_pnl: 0,
};

describe('the rail Flatten reports on the ticket (QA R32)', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.close.mockReset();
    mocks.notify.mockReset();
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  async function flatten() {
    await act(async () => {
      root.render(
        <TopOfBookProvider>
          <TickerTradeActionBar
            symbol="GRML" mode="paper" connected spendStatus="paper_armed"
            position={POSITION} summary={SUMMARY} referencePrice={9.3} variant="rail"
          />
        </TopOfBookProvider>,
      );
    });
    const button = mount.querySelector('.ticker-trade-close-btn') as HTMLButtonElement;
    expect(button.textContent).toBe('Flatten 2');
    await act(async () => { button.click(); });
    await act(async () => { await Promise.resolve(); });
  }

  it('shows the Flatten order on the ticket\'s Last line', async () => {
    mocks.close.mockResolvedValue({ ok: true, order_id: 9, side: 'SELL', qty: 2, mode: 'paper', outside_rth: false, order_type: 'MKT' });
    await flatten();
    expect(mocks.close).toHaveBeenCalledWith('GRML', 2, expect.objectContaining({ mode: 'paper' }));
    const last = mount.querySelector('[data-testid="manual-order-result"]');
    expect(last?.textContent).toContain('Flatten order #9');
  });

  it('shows a refusal there too, besides the dialog', async () => {
    const error = 'GRML is already being closed: 2 shares working (#11) -- cancel that order first, or use KILL';
    mocks.close.mockResolvedValue({ ok: false, error, place: { ok: false, reason_code: 'FLATTEN_NOT_A_CLOSE' } });
    await flatten();
    const last = mount.querySelector('[data-testid="manual-order-result"]');
    expect(last?.textContent).toContain('already being closed');
    expect(last?.className).toContain('err');
    expect(mocks.notify).toHaveBeenCalledOnce();
  });
});
