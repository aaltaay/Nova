/** @vitest-environment jsdom */
import { act } from 'react';
import { fireEvent } from '@testing-library/react';
import { createRoot, type Root } from 'react-dom/client';
import { CAPTURE_STOP_HOLD_MS } from '../capture/constants';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BotSymbolMenuHost } from './BotSymbolMenu';
import { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';
import { _resetIbkrStatusPollerForTests, _setIbkrStatusPollerFetchForTests } from '../ibkr/ibkrStatusPoller';

const command = vi.hoisted(() => vi.fn());
vi.mock('../api/novaFetch', () => ({ novaFetch: command }));
const toggle = vi.hoisted(() => vi.fn());
vi.mock('./useBotAllowlist', () => ({ useBotAllowlist: () => ({
  isAllowed: () => false, add: vi.fn(), remove: vi.fn(), toggle,
}) }));
// Today's hot list (ADR 043) is its own store: GRML is on it, AAPL is not.
const hot = vi.hoisted(() => ({
  state: { view: { entries: [{ symbol: 'GRML' }] }, error: null as string | null, busy: false },
  star: vi.fn(async () => null as string | null),
  unstar: vi.fn(async () => null as string | null),
}));
vi.mock('../hot_list', () => ({
  useHotList: () => hot.state,
  listedOn: (view: { entries: { symbol: string }[] } | null, symbol: string) => (view ? view.entries.some(e => e.symbol === symbol) : null),
  hotListActions: { star: hot.star, unstar: hot.unstar },
}));
const response = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;
let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  sessionStorage.clear();
  _resetIbkrStatusPollerForTests();
  command.mockReset();
  toggle.mockReset();
  hot.star.mockReset().mockResolvedValue(null);
  hot.unstar.mockReset().mockResolvedValue(null);
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

describe('Let the bot trade it (ADR 042 F)', () => {
  it('names the stock, waits for the answer, and keeps a refusal on screen in the backend’s words', async () => {
    toggle.mockResolvedValueOnce({ session: null, error: 'Nova places for a stock only on Paper and Sim' });
    await open();
    const row = container.querySelector('[data-testid="bot-symbol-menu-toggle"]') as HTMLButtonElement;
    expect(row.textContent).toContain('Let the bot trade AAPL (Nova buys and sells)');
    await act(async () => { row.click(); });
    expect(toggle).toHaveBeenCalledWith('AAPL', 'add', true);
    expect(container.querySelector('[data-testid="bot-symbol-menu-bot-error"]')?.textContent)
      .toBe('Nova places for a stock only on Paper and Sim');
    expect(container.querySelector('[role="menu"]')).not.toBeNull();
    toggle.mockResolvedValueOnce({ session: {}, error: null });
    await act(async () => { (container.querySelector('[data-testid="bot-symbol-menu-toggle"]') as HTMLButtonElement).click(); });
    expect(container.querySelector('[role="menu"]')).toBeNull();
  });
});

describe('★ Today\'s hot list (ADR 043)', () => {
  it('stars a stock from anywhere, takes one off, and keeps a refusal on screen', async () => {
    await open();
    const row = () => container.querySelector('[data-testid="bot-symbol-menu-hot"]') as HTMLButtonElement;
    expect(row().textContent).toContain('★ AAPL on today\'s hot list');
    await act(async () => { row().click(); });
    expect(hot.star).toHaveBeenCalledWith('AAPL');
    expect(container.querySelector('[data-testid="bot-symbol-menu"]')).toBeNull();
    act(() => openBotSymbolMenu('GRML', 0, 0));
    expect(row().textContent).toContain('Take GRML off today\'s hot list');
    expect(row().textContent).toContain('Hot list');
    hot.unstar.mockResolvedValueOnce('Nova holds GRML: take over the exit first');
    await act(async () => { row().click(); });
    expect(hot.unstar).toHaveBeenCalledWith('GRML');
    expect(container.querySelector('[data-testid="bot-symbol-menu-hot-error"]')?.textContent)
      .toBe('Nova holds GRML: take over the exit first');
  });

  it('says so while today\'s list has not been read', async () => {
    const before = hot.state;
    hot.state = { view: null as never, error: null, busy: false };
    await open();
    const row = container.querySelector('[data-testid="bot-symbol-menu-hot"]') as HTMLButtonElement;
    expect(row.disabled).toBe(true);
    expect(row.getAttribute('data-why')).toBe('Reading today\'s hot list…');
    hot.state = before;
  });
});
