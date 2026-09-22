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
    expect(container.textContent).toContain('Hold to stop recording AAPL');
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
