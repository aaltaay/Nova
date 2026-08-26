/**
 * @vitest-environment jsdom
 *
 * openOnRowClick=false (tables with a sibling SymbolSelectButton): the row
 * body only selects the symbol. Default (true): row click still opens
 * Trader too, for tables with no ticker button (Positions, Orders, ...).
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SelectableTableRow } from './SelectableTableRow';

describe('SelectableTableRow', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('table');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function renderRow(openOnRowClick: boolean | undefined) {
    const onSelect = vi.fn();
    const onOpenTrading = vi.fn();
    act(() => {
      root.render(
        <tbody>
          <SelectableTableRow
            symbol="AAPL"
            selected={false}
            onSelect={onSelect}
            onOpenTrading={onOpenTrading}
            openOnRowClick={openOnRowClick}
          >
            <td>AAPL</td>
          </SelectableTableRow>
        </tbody>,
      );
    });
    return { onSelect, onOpenTrading };
  }

  it('default (no ticker button): row click selects and opens Trader', () => {
    const { onSelect, onOpenTrading } = renderRow(undefined);
    act(() => {
      (container.querySelector('tr') as HTMLTableRowElement).click();
    });
    expect(onSelect).toHaveBeenCalledWith('AAPL');
    expect(onOpenTrading).toHaveBeenCalledWith('AAPL');
  });

  it('openOnRowClick=false: row click only selects, never opens Trader', () => {
    const { onSelect, onOpenTrading } = renderRow(false);
    act(() => {
      (container.querySelector('tr') as HTMLTableRowElement).click();
    });
    expect(onSelect).toHaveBeenCalledWith('AAPL');
    expect(onOpenTrading).not.toHaveBeenCalled();
  });

  it('openOnRowClick=false: Enter key only selects, never opens Trader', () => {
    const { onSelect, onOpenTrading } = renderRow(false);
    const row = container.querySelector('tr') as HTMLTableRowElement;
    act(() => {
      row.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
      );
    });
    expect(onSelect).toHaveBeenCalledWith('AAPL');
    expect(onOpenTrading).not.toHaveBeenCalled();
  });

  it('openOnRowClick=false uses the Quote Panel hint copy, not the Trader hint', () => {
    renderRow(false);
    const row = container.querySelector('tr') as HTMLTableRowElement;
    expect(row.title).toMatch(/Quote Panel/);
    expect(row.title).not.toMatch(/replace the active tab/);
  });
});
