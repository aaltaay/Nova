/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GlobalBarTickerSearch } from './GlobalBarTickerSearch';

function mount(onLookup = vi.fn()) {
  render(
    <GlobalBarTickerSearch
      onLookup={onLookup}
      tabs={['AAPL', 'AMD']}
      positions={[{ symbol: 'AAL', qty: 25 }]}
    />,
  );
  const input = screen.getByTestId('global-bar-search-input') as HTMLInputElement;
  act(() => input.focus());
  return { onLookup, input };
}

function type(input: HTMLInputElement, text: string) {
  fireEvent.change(input, { target: { value: text } });
}

function rows(): string[] {
  return Array.from(document.body.querySelectorAll('[role="option"]')).map(
    (row) => `${row.getAttribute('data-testid')?.replace('global-bar-search-option-', '')}${row.getAttribute('aria-selected') === 'true' ? '*' : ''}`,
  );
}

afterEach(() => cleanup());

describe('GlobalBarTickerSearch', () => {
  it('lists what was typed first, then the desk symbols that start with it', () => {
    const { input } = mount();
    expect(rows()).toEqual([]);
    type(input, 'a');
    expect(input.value).toBe('A');
    expect(rows()).toEqual(['A*', 'AAPL', 'AMD', 'AAL']);
    expect(document.body.querySelector('[data-testid="global-bar-search-option-AAPL"]')?.textContent).toContain('Trader tab');
    expect(document.body.querySelector('[data-testid="global-bar-search-option-AAL"]')?.textContent).toContain('Position');
    expect(input.getAttribute('aria-expanded')).toBe('true');
  });

  it('Enter opens exactly what was typed by default, and closes the list', () => {
    const { input, onLookup } = mount();
    type(input, 'aa');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onLookup).toHaveBeenCalledWith('AA');
    expect(rows()).toEqual([]);
  });

  it('↓ then Enter opens the suggestion instead', () => {
    const { input, onLookup } = mount();
    type(input, 'aa');
    expect(rows()).toEqual(['AA*', 'AAPL', 'AAL']);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(rows()).toEqual(['AA', 'AAPL*', 'AAL']);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onLookup).toHaveBeenCalledWith('AAPL');
    expect(input.value).toBe('AAPL');
  });

  it('a click on a suggestion opens it', () => {
    const { input, onLookup } = mount();
    type(input, 'am');
    fireEvent.click(document.body.querySelector('[data-testid="global-bar-search-option-AMD"]')!);
    expect(onLookup).toHaveBeenCalledWith('AMD');
  });

  it('an exact desk symbol is not listed twice', () => {
    const { input, onLookup } = mount();
    type(input, 'amd');
    expect(rows()).toEqual(['AMD*']);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onLookup).toHaveBeenCalledWith('AMD');
  });

  it('coming back to the box selects the last symbol, so the next one replaces it', () => {
    const { input } = mount();
    type(input, 'msft');
    fireEvent.keyDown(input, { key: 'Enter' });
    act(() => input.blur());
    act(() => input.focus());
    expect(input.value).toBe('MSFT');
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, 4]);
  });

  it('Escape closes the list without opening anything', () => {
    const { input, onLookup } = mount();
    type(input, 'a');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(rows()).toEqual([]);
    expect(onLookup).not.toHaveBeenCalled();
  });
});
