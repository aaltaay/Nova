/**
 * QA R35 remainder (#459): a Nova Action's "Exit order #N" reached only the
 * quick bar's status line; the ticket's Last line kept naming the previous
 * order. The trade bar now forwards each outcome for its own symbol there --
 * a repeat of the same text included -- and the quick bar leaves it to it.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NovaActionOutcome } from '../hotkeys';
import { TopOfBookProvider } from '../hotkeys/TopOfBookContext';
import { TickerTradeActionBar } from './TickerTradeActionBar';
import type { IbkrAccountSummary, IbkrPosition } from './types';

const mocks = vi.hoisted(() => ({
  close: vi.fn(),
  lastResult: null as NovaActionOutcome | null,
  quickBar: vi.fn(),
}));

vi.mock('../ux', () => ({ confirmApp: async () => true, alertApp: async () => undefined }));
vi.mock('./useTradingPinGate', () => ({ useTradingPinGate: () => ({ ensureUnlocked: async () => true, pinDialog: null }) }));
vi.mock('./closeFullPosition', () => ({ closeFullPosition: (...args: unknown[]) => mocks.close(...args) }));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: vi.fn() }));
vi.mock('../hotkeys/NovaActionRuntimeSync', () => ({ NovaActionRuntimeSync: () => null }));
vi.mock('../hotkeys/TradingQuickBar', () => ({
  TradingQuickBar: (props: { status?: boolean }) => {
    mocks.quickBar(props);
    return null;
  },
}));
vi.mock('../hotkeys/HotkeyDispatchContext', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hotkeys/HotkeyDispatchContext')>()),
  useHotkeyDispatchOptional: () => ({ lastResult: mocks.lastResult }),
}));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, mode: 'paper', spend_status: 'paper_armed', short_enabled: false }),
}));

const SUMMARY = { connected: true, NetLiquidation: 100_000, BuyingPower: 400_000 } as IbkrAccountSummary;
const POSITION: IbkrPosition = {
  symbol: 'GRML', qty: 2, market_price: 9.3, market_value: 18.6, avg_cost: 9.2, unrealized_pnl: 0.2, realized_pnl: 0,
};

describe('a Nova Action reports on the ticket (QA R35)', () => {
  let mount: HTMLDivElement;
  let root: Root;
  let seq = 0;

  beforeEach(() => {
    mocks.close.mockReset();
    mocks.quickBar.mockReset();
    mocks.lastResult = null;
    seq = 0;
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  function render() {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <TickerTradeActionBar
            symbol="GRML" mode="paper" connected spendStatus="paper_armed"
            position={POSITION} summary={SUMMARY} referencePrice={9.3} variant="rail"
          />
        </TopOfBookProvider>,
      );
    });
  }

  /** The dispatcher publishes an outcome; the bar re-reads its context. */
  function publish(outcome: Omit<NovaActionOutcome, 'seq'>) {
    seq += 1;
    mocks.lastResult = { ...outcome, seq };
    render();
  }

  const last = () => mount.querySelector('[data-testid="manual-order-result"]');

  it('shows the outcome for this symbol on the Last line, and the quick bar leaves it there', () => {
    render();
    expect(last()).toBeNull();
    publish({ ok: true, text: 'Exit order #12', symbol: 'GRML' });
    expect(last()?.textContent).toContain('Exit order #12');
    expect(last()?.className).toContain('ok');
    expect(mocks.quickBar).toHaveBeenLastCalledWith({ status: false });
  });

  it('shows a refusal too', () => {
    render();
    publish({ ok: false, text: 'No position to exit', symbol: 'GRML' });
    expect(last()?.textContent).toContain('No position to exit');
    expect(last()?.className).toContain('err');
  });

  it('ignores an outcome for another symbol, and one published before the ticket mounted', () => {
    publish({ ok: true, text: 'Exit order #3', symbol: 'GRML' });
    expect(last()).toBeNull();
    publish({ ok: true, text: 'Exit order #4', symbol: 'AAPL' });
    expect(last()).toBeNull();
  });

  it('shows a repeat of the same text after another outcome took the line', async () => {
    render();
    publish({ ok: true, text: 'Exit order #12', symbol: 'GRML' });
    mocks.close.mockResolvedValue({ ok: true, order_id: 9, side: 'SELL', qty: 2, mode: 'paper', outside_rth: false, order_type: 'MKT' });
    await act(async () => { (mount.querySelector('.ticker-trade-close-btn') as HTMLButtonElement).click(); });
    await act(async () => { await Promise.resolve(); });
    expect(last()?.textContent).toContain('Flatten order #9');
    publish({ ok: true, text: 'Exit order #12', symbol: 'GRML' });
    expect(last()?.textContent).toContain('Exit order #12');
  });
});
