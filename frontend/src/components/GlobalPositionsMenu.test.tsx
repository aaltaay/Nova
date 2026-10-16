/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { IbkrPosition } from '../ibkr/types';
import { GlobalPositionsMenu } from './GlobalPositionsMenu';
import { heldPositionRows } from './globalPositionsRows';

const pos = (symbol: string, qty: number, extra: Partial<IbkrPosition> = {}): IbkrPosition => ({
  symbol,
  qty,
  market_price: null,
  market_value: null,
  avg_cost: 2.5,
  unrealized_pnl: 1.25,
  realized_pnl: null,
  ...extra,
});

afterEach(cleanup);

describe('heldPositionRows', () => {
  it('keeps only held stocks, one row per symbol, longs and shorts', () => {
    const rows = heldPositionRows([
      pos('zzz', 100),
      pos('FLAT', 0),
      pos('SHRT', -200, { unrealized_pnl: -3 }),
      pos('', 50),
      pos('NAN', Number.NaN),
    ]);
    expect(rows.map((r) => [r.symbol, r.qty])).toEqual([['SHRT', -200], ['ZZZ', 100]]);
  });

  it('adds two rows for one symbol and never invents their open P&L', () => {
    const [row] = heldPositionRows([pos('ABC', 100), pos('ABC', 50, { unrealized_pnl: null })]);
    expect(row).toEqual({ symbol: 'ABC', qty: 150, avgCost: null, openPnl: null });
  });
});

describe('GlobalPositionsMenu', () => {
  const base = { stale: false, traderActive: false, closeTraderView: () => {}, onClose: () => {} };

  it('lists each position and opens it in the Trader on click', () => {
    const onOpen = vi.fn();
    const onClose = vi.fn();
    const rows = heldPositionRows([pos('SPCX', -300, { unrealized_pnl: null }), pos('AAPL', 10)]);
    render(<GlobalPositionsMenu {...base} rows={rows} onOpenSymbol={onOpen} onClose={onClose} />);
    const short = screen.getByTestId('global-position-SPCX');
    expect(short.textContent).toContain('300 short');
    expect(short.textContent).toContain('--');
    expect(screen.getByTestId('global-position-AAPL').textContent).toContain('+$1.25');
    fireEvent.click(short);
    expect(onClose).toHaveBeenCalled();
    expect(onOpen).toHaveBeenCalledWith('SPCX');
  });

  it('says so when nothing is held, and when the rows are last known', () => {
    render(<GlobalPositionsMenu {...base} stale rows={[]} onOpenSymbol={() => {}} />);
    expect(screen.getByTestId('global-positions-empty').textContent).toContain('No open positions');
    expect(screen.getByTestId('global-positions-menu').textContent).toContain('Last known');
  });
});
