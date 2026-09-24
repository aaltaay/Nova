/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PositionsPanel } from './PositionsPanel';
import type { IbkrPosition } from './types';

const position = (symbol: string, qty: number): IbkrPosition => ({
  symbol,
  qty,
  market_price: null,
  market_value: null,
  avg_cost: null,
  commission: null,
  unrealized_pnl: null,
  realized_pnl: null,
});

const POSITIONS = [position('GCTK', 5), position('APUS', -10), position('PFSA', 20)];

function renderPanel() {
  render(
    <PositionsPanel
      summary={null}
      positions={POSITIONS}
      orders={[]}
      selectedSymbol={null}
      onSelectSymbol={vi.fn()}
      onOpenTrading={vi.fn()}
      compact
    />,
  );
}

const order = () =>
  [...screen.getByTestId('positions-table').querySelectorAll('tbody tr')].map(
    (tr) => tr.querySelector('.ibkr-symbol')?.textContent,
  );
const header = (id: string) =>
  screen.getByTestId('positions-table').querySelector(`th[data-column-id="${id}"]`) as HTMLElement;

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('PositionsPanel click-to-sort', () => {
  it('sorts by quantity highest first, then lowest first, then the broker order', () => {
    renderPanel();
    expect(order()).toEqual(['GCTK', 'APUS', 'PFSA']);
    act(() => fireEvent.click(header('qty')));
    expect(order()).toEqual(['PFSA', 'GCTK', 'APUS']);
    expect(header('qty').getAttribute('aria-sort')).toBe('descending');
    act(() => fireEvent.click(header('qty')));
    expect(order()).toEqual(['APUS', 'GCTK', 'PFSA']);
    act(() => fireEvent.click(header('qty')));
    expect(order()).toEqual(['GCTK', 'APUS', 'PFSA']);
    expect(header('qty').getAttribute('aria-sort')).toBe('none');
  });

  it('sorts symbols A to Z first', () => {
    renderPanel();
    act(() => fireEvent.click(header('symbol')));
    expect(order()).toEqual(['APUS', 'GCTK', 'PFSA']);
  });

  it('sorts the columns the order tables do not have, an unknown P&L last', () => {
    POSITIONS[0] = { ...position('GCTK', 5), unrealized_pnl: 12.5 };
    POSITIONS[1] = { ...position('APUS', -10), unrealized_pnl: -40 };
    try {
      renderPanel();
      expect(header('unrealized').title).toMatch(/Click to sort · Drag to reorder columns$/);
      act(() => fireEvent.click(header('unrealized')));
      expect(order()).toEqual(['GCTK', 'APUS', 'PFSA']);
      act(() => fireEvent.click(header('unrealized')));
      expect(order()).toEqual(['APUS', 'GCTK', 'PFSA']);
      expect(header('mkt_value').getAttribute('aria-sort')).toBe('none');
    } finally {
      POSITIONS[0] = position('GCTK', 5);
      POSITIONS[1] = position('APUS', -10);
    }
  });
});
