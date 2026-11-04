/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OWNER_BOTS_UNREAD } from '../constantGroups/owners';
import type { DeskPosition } from './deskPositions';
import { PositionsPanel } from './PositionsPanel';

const closeBots = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('../account/ownersApi', () => ({ closeBots }));

const row = (symbol: string, qty: number, extra: Partial<DeskPosition> = {}): DeskPosition => ({
  symbol, qty, market_price: 124.89, market_value: qty * 124.89, avg_cost: 125.9, unrealized_pnl: 19.19, realized_pnl: null,
  ...extra,
});
const bots = (symbol: string, qty: number, bot: string, bots_qty = qty) => row(symbol, qty, { owner: 'bots', bot, bots_qty });

function renderPanel(positions: DeskPosition[], props: { botsStale?: boolean; onOpenTrading?: () => void } = {}) {
  render(
    <PositionsPanel
      summary={null}
      positions={positions}
      orders={[]}
      selectedSymbol={null}
      onSelectSymbol={vi.fn()}
      onOpenTrading={props.onOpenTrading ?? vi.fn()}
      botsStale={props.botsStale}
      mode="paper"
      connected
      compact
    />,
  );
}

const headers = () => [...screen.getByTestId('positions-table').querySelectorAll('th')]
  .map((th) => th.textContent?.replace('↕', ''));
const rowOf = (text: string) => screen.getByText(text).closest('tr') as HTMLElement;

afterEach(() => {
  cleanup();
  closeBots.mockClear();
  localStorage.clear();
});

describe('PositionsPanel with both books (ADR 069 decision 9)', () => {
  it("lists the bots' row beside yours and says whose each is", () => {
    renderPanel([row('INTC', 100, { owner: 'you', bot: null }), bots('ORCL', -19, 'live_trader')]);
    expect(headers().slice(0, 3)).toEqual(['Symbol', 'Whose', 'Side']);
    expect(screen.getByTestId('positions-table').className).toContain('ibkr-table--whose');
    expect(within(rowOf('INTC')).getByTestId('account-whose').textContent).toBe('You');
    expect(within(rowOf('ORCL')).getByTestId('account-whose').textContent).toBe('Live Trader');
  });

  it("gives a bots' row their Close and never your Sell; your row keeps yours", () => {
    renderPanel([row('INTC', 100, { owner: 'you', bot: null }), bots('ORCL', -19, 'live_trader')]);
    expect(within(rowOf('INTC')).queryByTestId('close-position-btn')).not.toBeNull();
    expect(within(rowOf('ORCL')).queryByTestId('close-position-btn')).toBeNull();
    expect(within(rowOf('ORCL')).getByTestId('account-close-bots-ORCL').textContent).toBe('Close');
  });

  it("asks once, in a short's words, then closes the bots' shares; the row never opens the Trader", async () => {
    const onOpenTrading = vi.fn();
    renderPanel([bots('ORCL', -19, 'live_trader')], { onOpenTrading });
    const close = screen.getByTestId('account-close-bots-ORCL');
    fireEvent.click(close);
    expect(close.textContent).toBe('Buy back all 19?');
    expect(closeBots).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(close); });
    expect(closeBots).toHaveBeenCalledWith('ORCL');
    expect(onOpenTrading).not.toHaveBeenCalled();
  });

  it("puts one Close on a stock two bots hold, for every bot's shares", () => {
    renderPanel([bots('ORCL', -19, 'live_trader', -24), bots('ORCL', -5, 'claude', -24)]);
    const closes = screen.getAllByTestId('account-close-bots-ORCL');
    expect(closes).toHaveLength(1);
    fireEvent.click(closes[0]);
    expect(closes[0].textContent).toBe('Buy back all 24?');
  });

  it('keeps today\'s table where there is one book', () => {
    renderPanel([row('INTC', 100)]);
    expect(headers()).not.toContain('Whose');
    expect(screen.getByTestId('positions-table').className).not.toContain('ibkr-table--whose');
    expect(screen.queryByTestId('account-whose')).toBeNull();
  });

  it("never says nothing is held while the bots' shares cannot be read, and your Close stays", () => {
    renderPanel([], { botsStale: true });
    expect(screen.getByTestId('positions-bots-unread').textContent).toBe(OWNER_BOTS_UNREAD);
    expect(screen.queryByTestId('positions-empty')).toBeNull();
    cleanup();
    const mine = [row('INTC', 100, { owner: 'you', bot: null })];
    const why = () => screen.getByTestId('close-position-btn').getAttribute('data-why');
    renderPanel(mine);
    const read = why();
    cleanup();
    renderPanel(mine, { botsStale: true });
    expect(why()).toBe(read);
  });
});
