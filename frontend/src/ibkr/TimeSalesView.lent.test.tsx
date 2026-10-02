/**
 * @vitest-environment jsdom
 *
 * A Time & Sales whose line went with the tab's Level 2 to one of Nova's setups (ADR 044
 * decision 6) reads LENT and says whose setup took it and when it comes back -- in place of the
 * rows, as the ladder does. A lent line is not a fault.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TimeSalesView } from './TimeSalesView';
import type { TapeState } from './tapeFeed';

const LENT: TapeState = {
  prints: [],
  connected: false,
  error: null,
  lent: { symbol: 'AISP', setupType: 'first_pullback', tier: 'near', why: 'near its trigger', since: 1, text: null },
};

const WORDS =
  "Time & Sales lent to AISP's first pullback (near its trigger) — back when it ends or when you bring this tab to the front";

describe('Time & Sales with a lent line', () => {
  let container: HTMLDivElement;
  let root: Root;

  function render(feed: TapeState, embedded = true) {
    act(() => {
      root.render(<TimeSalesView symbol="ABC" feed={feed} embedded={embedded} statusTitle="IBKR feed" />);
    });
  }

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
  });

  it('says whose setup took the line, in place of the rows, and reads LENT', () => {
    render(LENT);
    const words = container.querySelector('[data-testid="ts-lent"]');
    expect(words?.textContent).toBe(WORDS);
    expect(words?.getAttribute('role')).toBe('status');
    const status = container.querySelector('[data-testid="ts-status"]');
    expect(status?.textContent).toBe('LENT');
    expect(status?.getAttribute('title')).toBe(WORDS);
    expect(status?.className).toContain('ts-panel__status--off');
    expect(container.querySelectorAll('.ts-row')).toHaveLength(0);
    expect(container.textContent).not.toContain('ERROR');
    expect(container.textContent).not.toContain('Connecting');
  });

  it('the standalone panel says it too', () => {
    render(LENT, false);
    expect(container.querySelector('[data-testid="ts-lent"]')?.textContent).toBe(WORDS);
  });

  it('a line IBKR refused that the backend is asking for again reads RETRYING, with its words (#698)', () => {
    const words = 'IBKR refused this Time & Sales: every tick-by-tick line is in use (IB error 10190); '
      + "auto-record gave back SSM's recording line. Asking again at 07:54:20 ET.";
    render({ prints: [], connected: false, error: words, lent: null, retryAt: 1790942060 });
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('RETRYING');
    expect(container.textContent).toContain('Asking again at 07:54:20 ET.');
    render({ prints: [], connected: false, error: 'Tape error', lent: null, retryAt: null });
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('ERROR');
  });

  it('a line that is not lent reads as before', () => {
    render({ prints: [], connected: true, error: null, lent: null });
    expect(container.querySelector('[data-testid="ts-lent"]')).toBeNull();
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('LIVE');
    expect(container.querySelector('[data-testid="ts-status"]')?.getAttribute('title')).toBe('IBKR feed');
  });
});
