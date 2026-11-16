/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ownerYoursToClose } from '../constantGroups/owners';
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

describe('heldPositionRows with every book (ADR 072)', () => {
  it('gives each holder of a stock its own row, in book order, and never adds them', () => {
    const rows = heldPositionRows([
      { ...pos('ORCL', -19), owner: 'earlier_bots', bot: 'live_trader' },
      { ...pos('ORCL', 30), owner: 'brain', bot: null },
      { ...pos('ORCL', 100), owner: 'you', bot: null },
      { ...pos('ORCL', -5), owner: 'claude', bot: null },
      { ...pos('AAPL', 10), owner: 'you', bot: null },
    ]);
    expect(rows.map((r) => [r.symbol, r.qty, r.bot ?? r.owner])).toEqual([
      ['AAPL', 10, 'you'], ['ORCL', 100, 'you'], ['ORCL', -5, 'claude'], ['ORCL', 30, 'brain'],
      ['ORCL', -19, 'live_trader'],
    ]);
  });

  it('keeps how many of your shares were handed to you, and by whom', () => {
    const [row] = heldPositionRows([{ ...pos('XLAB', 200), owner: 'you', bot: null, handed_qty: 200, handed_from: 'brain' }]);
    expect(row).toMatchObject({ owner: 'you', handed_qty: 200, handed_from: 'brain' });
  });
});

describe('GlobalPositionsMenu', () => {
  const base = { stale: false, traderActive: false, closeTraderView: () => {}, onClose: () => {} };

  it("says whose each row is on Paper, and another trader's row still opens the stock", () => {
    const onOpenSymbol = vi.fn();
    const rows = heldPositionRows([
      { ...pos('ORCL', -19, { avg_cost: 125.9, unrealized_pnl: 19.19 }), owner: 'claude', bot: null },
      { ...pos('ORCL', 100), owner: 'you', bot: null },
    ]);
    render(<GlobalPositionsMenu {...base} rows={rows} onOpenSymbol={onOpenSymbol} />);
    expect(screen.getAllByTestId('account-whose').map((chip) => chip.textContent)).toEqual(['You', 'Claude']);
    const theirs = screen.getByTestId('global-position-ORCL-claude');
    expect(theirs.textContent).toContain('19 short @ $125.90');
    fireEvent.click(theirs);
    expect(onOpenSymbol).toHaveBeenCalledWith('ORCL');
  });

  it("says whose the shares handed to you were, dashed, and no You chip when every share was handed", () => {
    const rows = heldPositionRows([{ ...pos('XLAB', 200), owner: 'you', bot: null, handed_qty: 200, handed_from: 'brain' }]);
    render(<GlobalPositionsMenu {...base} rows={rows} onOpenSymbol={() => {}} />);
    const chips = screen.getAllByTestId('account-whose');
    expect(chips).toHaveLength(1);
    expect(chips[0].textContent).toBe(ownerYoursToClose('brain'));
    expect(chips[0].className).toContain('is-handed');
    expect(chips[0].getAttribute('data-owner')).toBe('brain');
  });

  it('draws no chip where there is one book', () => {
    render(<GlobalPositionsMenu {...base} rows={heldPositionRows([pos('ORCL', 100)])} onOpenSymbol={() => {}} />);
    expect(screen.queryByTestId('account-whose')).toBeNull();
    expect(screen.getByTestId('global-position-ORCL').className).not.toContain('has-whose');
  });

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

  it('says so when nothing is held', () => {
    render(<GlobalPositionsMenu {...base} rows={[]} onOpenSymbol={() => {}} />);
    expect(screen.getByTestId('global-positions-empty').textContent).toContain('No open positions');
  });

  it('marks last-known rows, and never says nothing is held when it has no read', () => {
    render(<GlobalPositionsMenu {...base} stale rows={heldPositionRows([pos('ABC', 10)])} onOpenSymbol={() => {}} />);
    expect(screen.getByTestId('global-positions-menu').textContent).toContain('Last known');
    cleanup();
    render(<GlobalPositionsMenu {...base} stale rows={[]} onOpenSymbol={() => {}} />);
    expect(screen.getByTestId('global-positions-empty').textContent).toContain('Positions not read');
    expect(screen.getByTestId('global-positions-empty').textContent).not.toContain('No open positions');
  });

  it('keeps a fractional IBKR leftover visible, never rounded to 0', () => {
    render(<GlobalPositionsMenu {...base} rows={heldPositionRows([pos('FRAC', 0.0004)])} onOpenSymbol={() => {}} />);
    expect(screen.getByTestId('global-position-FRAC').textContent).toContain('0.0004');
  });
});
