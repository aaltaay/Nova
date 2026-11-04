/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { DeskPosition, IbkrPosition } from '../ibkr';
import { StockViewDockFooter } from './StockViewDockFooter';

const yours: IbkrPosition = {
  symbol: 'ORCL', qty: 100, market_price: 124.89, market_value: 12489, avg_cost: 124.5, unrealized_pnl: 39, realized_pnl: null,
};
const bots: DeskPosition = {
  symbol: 'ORCL', qty: -19, market_price: 124.89, market_value: -2372.91, avg_cost: 125.9, unrealized_pnl: 19.19,
  realized_pnl: null, owner: 'bots', bot: 'live_trader',
};

const text = () => screen.getByTestId('stock-view-dock-footer').textContent ?? '';

afterEach(cleanup);

describe('StockViewDockFooter (ADR 069 decision 9)', () => {
  it("says the bots' shares in the stock, with whose they are", () => {
    render(<StockViewDockFooter symbol="ORCL" mode="paper" position={null} botsRows={[bots]} />);
    expect(text()).toContain('ORCL -19 @ 125.90');
    expect(screen.getByTestId('account-whose').textContent).toBe('Live Trader');
    expect(text()).not.toContain('No open position');
  });

  it("puts yours first, and the bots' beside it", () => {
    render(<StockViewDockFooter symbol="ORCL" mode="paper" position={yours} botsRows={[bots]} />);
    expect(text().indexOf('ORCL +100')).toBeLessThan(text().indexOf('ORCL -19'));
  });

  it('keeps the line as it was with nothing of the bots', () => {
    render(<StockViewDockFooter symbol="ORCL" mode="live" position={yours} />);
    expect(text()).toContain('ORCL +100 @ 124.50');
    expect(screen.queryByTestId('account-whose')).toBeNull();
  });

  it('says nothing is held only when nobody holds it', () => {
    render(<StockViewDockFooter symbol="ORCL" mode="paper" position={null} />);
    expect(text()).toContain('No open position · ORCL');
  });
});
