/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TAPE_MIN_SIZE_STORAGE_KEY, TAPE_UI_MAX_ROWS } from '../constants';
import { TimeSalesPanel } from './TimeSalesPanel';
import type { TapePrint, TapeSilence } from './tapeFeed';
import { writeTapeMinSize } from './tapeMinSizeFilter';

function makePrints(n: number, size = 100): TapePrint[] {
  return Array.from({ length: n }, (_, i) => ({
    symbol: 'AAPL',
    time: `2026-09-18T13:00:${String(59 - (i % 60)).padStart(2, '0')}.${String(i).padStart(3, '0')}Z`,
    price: n - i,
    size,
    exchange: 'ISLAND',
    side: 'ask' as const,
  }));
}

function mixedPrints(): TapePrint[] {
  return [10, 50, 100, 500].map((size, i) => ({
    symbol: 'QNME',
    time: `2026-09-18T15:33:3${i}.000Z`,
    price: 0.82,
    size,
    exchange: 'ISLAND',
    side: 'ask' as const,
  }));
}

const tapeMock = {
  prints: makePrints(TAPE_UI_MAX_ROWS),
  connected: true,
  error: null as string | null,
  silence: null as TapeSilence | null,
};

vi.mock('./useIbkrTape', () => ({
  useIbkrTape: () => tapeMock,
}));

const gapMock: { badge: import('./feedPulse').FeedGapBadge | null } = { badge: null };

vi.mock('./feedPulseStore', () => ({
  useFeedGapBadge: () => gapMock.badge,
}));

function renderedSizes(root: ParentNode): number[] {
  return [...root.querySelectorAll('[data-testid="ts-size"]')].map((el) =>
    Number(el.getAttribute('data-size')),
  );
}

function openFilter(target: Element) {
  act(() => {
    target.dispatchEvent(
      new MouseEvent('contextmenu', {
        bubbles: true,
        cancelable: true,
        button: 2,
        clientX: 24,
        clientY: 36,
      }),
    );
  });
}

describe('TimeSalesPanel virtual window', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    tapeMock.prints = makePrints(TAPE_UI_MAX_ROWS);
    tapeMock.connected = true;
    tapeMock.error = null;
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

  it('keeps the full ring but mounts only a viewport window of rows', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="AAPL" />);
    });
    const rows = container.querySelector('[data-testid="ts-panel-rows"]');
    expect(rows?.getAttribute('data-ring-count')).toBe(String(TAPE_UI_MAX_ROWS));
    const rendered = Number(rows?.getAttribute('data-rendered-count'));
    expect(rendered).toBeGreaterThan(0);
    expect(rendered).toBeLessThan(TAPE_UI_MAX_ROWS);
    expect(container.querySelectorAll('.ts-row')).toHaveLength(rendered);
  });
});

describe('TimeSalesPanel min-size filter', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    tapeMock.prints = mixedPrints();
    tapeMock.connected = true;
    tapeMock.error = null;
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

  it('opens the filter UI from a right-click on the panel, header, or rows', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeNull();

    openFilter(container.querySelector('[data-testid="ts-panel"]')!);
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeTruthy();
    expect(document.querySelector('[data-testid="ts-min-size-input"]')).toBeTruthy();

    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeNull();

    openFilter(container.querySelector('.ts-panel__header')!);
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeTruthy();
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });

    openFilter(container.querySelector('[data-testid="ts-panel-rows"]')!);
    expect(document.querySelector('[data-testid="ts-min-size-filter"]')).toBeTruthy();
  });

  it('hides prints smaller than the typed min size', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    openFilter(container.querySelector('[data-testid="ts-panel"]')!);
    const input = document.querySelector('[data-testid="ts-min-size-input"]') as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: '100' } });
    });
    expect(renderedSizes(container)).toEqual([100, 500]);
    expect(container.querySelector('[data-testid="ts-panel-rows"]')?.getAttribute('data-ring-count')).toBe('4');
    expect(container.querySelector('[data-testid="ts-panel-rows"]')?.getAttribute('data-filtered-count')).toBe('2');
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')?.textContent).toBe('Size ≥ 100');
  });

  it('clears the filter when the box is empty or 0', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    openFilter(container.querySelector('[data-testid="ts-panel"]')!);
    const input = document.querySelector('[data-testid="ts-min-size-input"]') as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: '100' } });
    });
    expect(renderedSizes(container)).toEqual([100, 500]);
    act(() => {
      fireEvent.change(input, { target: { value: '' } });
    });
    expect(renderedSizes(container)).toEqual([10, 50, 100, 500]);
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')).toBeNull();
    expect(JSON.parse(localStorage.getItem(TAPE_MIN_SIZE_STORAGE_KEY) ?? '').value).toBe(0);
  });

  it('reloads the saved min size from localStorage on remount', () => {
    writeTapeMinSize(100);
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')?.textContent).toBe('Size ≥ 100');
    expect(renderedSizes(container)).toEqual([100, 500]);

    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    act(() => {
      root.render(<TimeSalesPanel symbol="QNME" />);
    });
    expect(container.querySelector('[data-testid="ts-min-size-badge"]')?.textContent).toBe('Size ≥ 100');
    expect(renderedSizes(container)).toEqual([100, 500]);
  });
});

describe('TimeSalesPanel feed gap badge (#672)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    tapeMock.prints = mixedPrints();
    tapeMock.connected = true;
    tapeMock.error = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    gapMock.badge = null;
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function status(): HTMLElement {
    return container.querySelector('[data-testid="ts-status"]') as HTMLElement;
  }

  it('says LIVE while data arrives', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="NXL" />);
    });
    expect(status().textContent).toBe('LIVE');
    expect(status().className).not.toContain('ts-panel__status--bad');
  });

  it('says NO DATA in red with the reason on hover while IBKR data has stopped', () => {
    gapMock.badge = { tone: 'bad', state: 'no-data', label: 'NO DATA 9s', title: 'No IBKR data on any line for 9 s.' };
    act(() => {
      root.render(<TimeSalesPanel symbol="NXL" />);
    });
    expect(status().textContent).toBe('NO DATA 9s');
    expect(status().className).toContain('ts-panel__status--bad');
    expect(status().getAttribute('title')).toBe('No IBKR data on any line for 9 s.');
  });

  it('leaves a capture replay badge alone: the recording is not the live feed', () => {
    gapMock.badge = { tone: 'bad', state: 'no-data', label: 'NO DATA 9s', title: 'x' };
    act(() => {
      root.render(<TimeSalesPanel symbol="NXL" connectedText="REPLAY" statusTitle="Session Record" />);
    });
    expect(status().textContent).toBe('REPLAY');
    expect(status().className).not.toContain('ts-panel__status--bad');
  });
});

describe('TimeSalesPanel -- a line that stopped printing says so (#722)', () => {
  // 2026-10-05: SAIQ's tape stopped at 09:35:42 ET while its Level 2 kept updating, and the pane read LIVE.
  const SINCE = Date.parse('2026-10-05T13:35:42Z') / 1000;
  const SILENT_TEXT = 'No prints since 09:35:42 ET while Level 2 kept updating: IBKR\'s tape line may be down. '
    + 'A quiet name looks the same; this clears on the next print.';
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-05T13:41:42Z'));
    tapeMock.prints = mixedPrints();
    tapeMock.connected = true;
    tapeMock.error = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    tapeMock.silence = null;
    gapMock.badge = null;
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
  });

  const status = () => container.querySelector('[data-testid="ts-status"]') as HTMLElement;
  const notice = () => container.querySelector('[data-testid="ts-silence"]');
  const render = () => act(() => {
    root.render(<TimeSalesPanel symbol="SAIQ" />);
  });

  it('reads SILENT with the seconds counting, in amber, and says why above the rows', () => {
    tapeMock.silence = { state: 'silent', since: SINCE, text: SILENT_TEXT };
    render();
    expect(status().textContent).toBe('SILENT 360s');
    expect(status().className).toContain('ts-panel__status--warn');
    expect(status().getAttribute('title')).toBe(SILENT_TEXT);
    expect(notice()?.textContent?.trim()).toBe('Silent since 09:35:42 while Level 2 moves: the line may be down');
    expect(notice()?.getAttribute('title')).toBe(SILENT_TEXT);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(status().textContent).toBe('SILENT 362s');
  });

  it('reads LINE DOWN in red when Level 1 counted trades the tape never printed', () => {
    const deadText = 'No prints since 09:35:42 ET while Level 1 shows trades up to 09:41:40 ET: '
      + "IBKR's tape line is down, not quiet. VEEA stopped printing in the same second: one IBKR "
      + 'tick-by-tick event, not this line alone.';
    tapeMock.silence = { state: 'dead', since: SINCE, text: deadText };
    render();
    expect(status().textContent).toBe('LINE DOWN 360s');
    expect(status().className).toContain('ts-panel__status--bad');
    expect(status().getAttribute('title')).toBe(deadText);
    expect(notice()?.textContent?.trim()).toBe("No prints since 09:35:42 while Level 1 trades: IBKR's tape line is down");
  });

  it('says HALTED for a halt, never that the line may be down', () => {
    tapeMock.silence = { state: 'halted', since: SINCE, text: 'Halted: no prints until it reopens. No prints since 09:35:42 ET.' };
    render();
    expect(status().textContent).toBe('HALTED');
    expect(notice()?.textContent?.trim()).toBe('Halted: no prints until it reopens');
  });

  it('a quiet name is a grey badge and nothing in the pane', () => {
    tapeMock.silence = { state: 'quiet', since: SINCE, text: 'No prints since 09:35:42 ET; Level 2 is quiet too.' };
    render();
    expect(status().textContent).toBe('QUIET 360s');
    expect(status().className).toContain('ts-panel__status--quiet');
    expect(notice()).toBeNull();
  });

  it('NO DATA on every line comes first', () => {
    tapeMock.silence = { state: 'silent', since: SINCE, text: SILENT_TEXT };
    gapMock.badge = { tone: 'bad', state: 'no-data', label: 'NO DATA 9s', title: 'No IBKR data on any line for 9 s.' };
    render();
    expect(status().textContent).toBe('NO DATA 9s');
    expect(notice()).toBeNull();
  });
});
