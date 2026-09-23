/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalBarTickerSearch } from './GlobalBarTickerSearch';
import { buildSymbolDirectory, resetSymbolDirectoryForTests } from './symbolDirectory';
import { resetRecentsForTests } from './tickerSearchRecents';

const LISTED = [
  ['AAPL', 'Apple Inc. Common Stock', 'NASDAQ'],
  ['APLE', 'Apple Hospitality REIT, Inc.', 'NYSE'],
  ['AA', 'Alcoa Corporation', 'NYSE'],
  ['QQQ', 'Invesco QQQ Trust, Series 1', 'NASDAQ'],
  ['SQQQ', 'ProShares UltraPro Short QQQ', 'NASDAQ'],
];

function withDirectory() {
  resetSymbolDirectoryForTests({ status: 'ready', directory: buildSymbolDirectory(LISTED), error: null });
}

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

function footer(): string | null {
  return document.body.querySelector('[data-testid="global-bar-search-footer"]')?.textContent ?? null;
}

beforeEach(() => {
  // No backend in tests: the directory load fails unless a test installs one.
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline'))));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  resetRecentsForTests();
  resetSymbolDirectoryForTests();
});

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

  it('focus lists the recent look-ups, newest first, and Shift+Delete forgets one', () => {
    const { input, onLookup } = mount();
    type(input, 'msft');
    fireEvent.keyDown(input, { key: 'Enter' });
    type(input, 'nvda');
    fireEvent.keyDown(input, { key: 'Enter' });
    act(() => input.blur());
    act(() => input.focus());
    expect(rows()).toEqual(['NVDA*', 'MSFT']);
    expect(document.body.textContent).toContain('Recent');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onLookup).toHaveBeenLastCalledWith('MSFT');
    act(() => input.blur());
    act(() => input.focus());
    expect(rows()).toEqual(['MSFT*', 'NVDA']);
    fireEvent.keyDown(input, { key: 'Delete', shiftKey: true });
    expect(rows()).toEqual(['NVDA*']);
    fireEvent.click(document.body.querySelector('[data-testid="global-bar-search-forget-NVDA"]')!);
    expect(rows()).toEqual([]);
  });

  it('finds a listed symbol by company name and makes it the default when the text is not a symbol', () => {
    withDirectory();
    const { input, onLookup } = mount();
    type(input, 'apple');
    expect(rows()).toEqual(['APPLE', 'AAPL*', 'APLE']);
    expect(document.body.querySelector('[data-testid="global-bar-search-option-APPLE"]')?.textContent).toContain('Not a listed symbol');
    expect(document.body.querySelector('[data-testid="global-bar-search-option-AAPL"]')?.textContent).toContain('Apple Inc.');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onLookup).toHaveBeenCalledWith('AAPL');
  });

  it('a listed symbol typed exactly stays the default over name matches', () => {
    withDirectory();
    const { input, onLookup } = mount();
    type(input, 'aa');
    expect(rows()[0]).toBe('AA*');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onLookup).toHaveBeenCalledWith('AA');
  });

  it('a regex filters every listed symbol, keeps its case, and counts the matches', () => {
    withDirectory();
    const { input } = mount();
    type(input, '/q{3}$/');
    expect(input.value).toBe('/q{3}$/');
    expect(rows()).toEqual(['QQQ*', 'SQQQ']);
    expect(footer()).toBe('Regex: 2 symbols match');
    type(input, '/(');
    expect(rows()).toEqual([]);
    expect(footer()).toMatch(/^Regex: /);
  });

  it('a wildcard filters symbols', () => {
    withDirectory();
    const { input } = mount();
    type(input, '?QQQ');
    expect(rows()).toEqual(['SQQQ*']);
  });

  it('Tab completes the picked suggestion into the box', () => {
    withDirectory();
    const { input, onLookup } = mount();
    type(input, 'aap');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Tab' });
    expect(input.value).toBe('AAPL');
    expect(onLookup).not.toHaveBeenCalled();
    expect(rows()[0]).toBe('AAPL*');
  });

  it('says when the listed-symbol directory is unavailable and keeps the desk symbols', async () => {
    const { input } = mount();
    await act(async () => {});
    type(input, 'a');
    expect(rows()).toEqual(['A*', 'AAPL', 'AMD', 'AAL']);
    expect(footer()).toContain('Listed symbols unavailable (offline)');
  });

  it('loads the directory on first focus', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ symbols: LISTED, error: null }))));
    vi.stubGlobal('fetch', fetchMock);
    const { input } = mount();
    await act(async () => {});
    expect(fetchMock).toHaveBeenCalledTimes(1);
    type(input, 'invesco');
    expect(rows()).toEqual(['INVESCO', 'QQQ*']);
    type(input, 'ultrapro short');
    expect(rows()).toEqual(['SQQQ*']);
  });
});
