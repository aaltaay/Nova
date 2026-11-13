/**
 * @vitest-environment jsdom
 *
 * A Time & Sales on a stock no lane is on (ADR 071) reads NO LANE and says where your lane is -- in place of the
 * rows, as the ladder does -- and a click on the words brings your lane here. It is not a fault.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LANE_BRING_EVENT } from '../constantGroups/market_ui';
import { TimeSalesView } from './TimeSalesView';
import type { TapeState } from './tapeFeed';

const WORDS = 'Your Time & Sales is on TGHL — click here or bring this tab to the front to have it on ABC';

const WAITING: TapeState = {
  prints: [],
  connected: false,
  error: null,
  laneWait: { you: 'TGHL', text: WORDS, plain: 'Your Time & Sales is on TGHL, not ABC' },
};

describe('Time & Sales on a stock no lane is on', () => {
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

  it('says where your lane is, in place of the rows, and reads NO LANE', () => {
    render(WAITING);
    const words = container.querySelector('[data-testid="ts-lane"]');
    expect(words?.textContent).toBe(WORDS);
    expect(words?.getAttribute('role')).toBe('button');
    const status = container.querySelector('[data-testid="ts-status"]');
    expect(status?.textContent).toBe('NO LANE');
    expect(status?.getAttribute('title')).toBe(WORDS);
    expect(status?.className).toContain('ts-panel__status--off');
    expect(container.querySelectorAll('.ts-row')).toHaveLength(0);
    expect(container.textContent).not.toContain('ERROR');
    expect(container.textContent).not.toContain('Connecting');
  });

  it('a click on the words asks for your lane here', () => {
    render(WAITING);
    const heard = vi.fn();
    const hear = (e: Event) => heard((e as CustomEvent<{ symbol: string }>).detail.symbol);
    window.addEventListener(LANE_BRING_EVENT, hear);
    act(() => (container.querySelector('[data-testid="ts-lane"]') as HTMLElement).click());
    window.removeEventListener(LANE_BRING_EVENT, hear);
    expect(heard).toHaveBeenCalledWith('ABC');
  });

  it('the standalone panel says it too', () => {
    render(WAITING, false);
    expect(container.querySelector('[data-testid="ts-lane"]')?.textContent).toBe(WORDS);
  });

  it('a line IBKR refused that the backend is asking for again reads RETRYING, with its words (#698)', () => {
    const words = 'IBKR refused this Time & Sales: every tick-by-tick line is in use (IB error 10190). '
      + 'Asking again at 07:54:20 ET.';
    render({ prints: [], connected: false, error: words, laneWait: null, retryAt: 1790942060 });
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('RETRYING');
    expect(container.textContent).toContain('Asking again at 07:54:20 ET.');
    render({ prints: [], connected: false, error: 'Tape error', laneWait: null, retryAt: null });
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('ERROR');
  });

  it('a stock a lane is on reads as before', () => {
    render({ prints: [], connected: true, error: null, laneWait: null });
    expect(container.querySelector('[data-testid="ts-lane"]')).toBeNull();
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('LIVE');
    expect(container.querySelector('[data-testid="ts-status"]')?.getAttribute('title')).toBe('IBKR feed');
  });
});
