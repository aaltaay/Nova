/** @vitest-environment jsdom */
import { act } from 'react';
import { fireEvent } from '@testing-library/react';
import { createRoot, type Root } from 'react-dom/client';
import { CAPTURE_STOP_HOLD_MS } from '../capture/constants';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BotSymbolMenuHost } from './BotSymbolMenu';
import { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';
import { getWatchList, resetWatchListForTests } from '../watch_list/watchListStore';
import { _resetIbkrStatusPollerForTests, _setIbkrStatusPollerFetchForTests } from '../ibkr/ibkrStatusPoller';

const command = vi.hoisted(() => vi.fn());
vi.mock('../api/novaFetch', () => ({ novaFetch: command }));
vi.mock('./useBotAllowlist', () => ({ useBotAllowlist: () => ({
  isAllowed: () => false, add: vi.fn(), remove: vi.fn(),
}) }));
const response = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;
let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  sessionStorage.clear();
  _resetIbkrStatusPollerForTests();
  command.mockReset();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => { root.unmount(); closeBotSymbolMenu(); });
  container.remove();
  _resetIbkrStatusPollerForTests();
  vi.restoreAllMocks();
});
async function open(recording = false) {
  _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response({
    enabled: true, connected: true, mode: 'paper',
    capture: recording, recording, capture_symbol: recording ? 'AAPL' : null,
  })));
  await act(async () => { root.render(<BotSymbolMenuHost />); });
  act(() => openBotSymbolMenu('AAPL', 0, 0));
}
async function clickRecord() {
  await act(async () => {
    (container.querySelector('[data-testid="bot-symbol-menu-record"]') as HTMLButtonElement).click();
  });
}
/** Stop is a hold, not a click (operator decision, 2026-09-21): press for the whole interval. */
async function holdStop() {
  const button = container.querySelector('[data-testid="bot-symbol-menu-record"]') as HTMLButtonElement;
  vi.useFakeTimers();
  try {
    fireEvent.pointerDown(button, { button: 0 });
    await act(async () => { vi.advanceTimersByTime(CAPTURE_STOP_HOLD_MS + 100); });
  } finally {
    vi.useRealTimers();
  }
  await act(async () => {});
}

describe('Record menu failures', () => {
  it('renders a start refusal and keeps the menu open', async () => {
    command.mockResolvedValue(response({ detail: 'Already recording TSLA; stop it first' }, false));
    await open();
    await clickRecord();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe('Already recording TSLA; stop it first');
    expect(container.querySelector('[role="menu"]')).not.toBeNull();
  });
  it('renders a stop failure instead of closing the menu', async () => {
    command.mockResolvedValue(response({ capture: true, error: 'Recorder stop failed' }));
    await open(true);
    const stop = container.querySelector('[data-testid="bot-symbol-menu-record"]') as HTMLButtonElement;
    expect(stop.getAttribute('aria-label')).toBe('Hold to stop recording AAPL');
    expect(stop.textContent).toContain('Hold to stop recording');
    expect(stop.textContent).toContain('REC');
    await clickRecord();  // a click never stops a recording
    expect(command).not.toHaveBeenCalled();
    await holdStop();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe('Recorder stop failed');
  });
  it('renders network failures and closes only after a successful retry', async () => {
    command.mockRejectedValueOnce(new Error('offline'));
    await open();
    await clickRecord();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Could not reach Nova');
    command.mockResolvedValue(response({ capture: true, capture_symbol: 'AAPL' }));
    await clickRecord();
    expect(container.querySelector('[role="menu"]')).toBeNull();
  });
});

it('offers Pin / Unpin first when a Trader tab opened it (ADR 011 preview tabs)', async () => {
  const onTogglePin = vi.fn();
  _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response({
    enabled: true, connected: true, mode: 'paper', capture: false, recording: false, capture_symbol: null,
  })));
  await act(async () => { root.render(<BotSymbolMenuHost />); });
  act(() => openBotSymbolMenu('AAPL', 0, 0, { pinned: false, onTogglePin }));
  const item = container.querySelector('[data-testid="bot-symbol-menu-pin"]') as HTMLButtonElement;
  expect(item.textContent).toContain('Pin tab');
  await act(async () => { item.click(); });
  expect(onTogglePin).toHaveBeenCalledTimes(1);
  expect(container.querySelector('[data-testid="bot-symbol-menu"]')).toBeNull();
  act(() => openBotSymbolMenu('AAPL', 0, 0, { pinned: true, onTogglePin }));
  expect((container.querySelector('[data-testid="bot-symbol-menu-pin"]') as HTMLButtonElement).textContent).toContain('Unpin tab');
  act(() => openBotSymbolMenu('AAPL', 0, 0));
  expect(container.querySelector('[data-testid="bot-symbol-menu-pin"]')).toBeNull();
});

it('adds the symbol to the watch list, and the next menu offers to remove it', async () => {
  localStorage.clear();
  resetWatchListForTests();
  await open();
  const item = () => container.querySelector('[data-testid="bot-symbol-menu-watch"]') as HTMLButtonElement;
  expect(container.querySelector('[data-testid="bot-symbol-menu-symbol"]')?.textContent).toBe('AAPL');
  expect(item().textContent).toContain('Add to watch list');
  expect(item().textContent).not.toContain('Watching');
  await act(async () => { item().click(); });
  expect(getWatchList()).toEqual(['AAPL']);
  expect(container.querySelector('[data-testid="bot-symbol-menu"]')).toBeNull();
  act(() => openBotSymbolMenu('AAPL', 0, 0));
  expect(item().textContent).toContain('Remove from watch list');
  expect(item().textContent).toContain('Watching');
  await act(async () => { item().click(); });
  expect(getWatchList()).toEqual([]);
  localStorage.clear();
  resetWatchListForTests();
});
