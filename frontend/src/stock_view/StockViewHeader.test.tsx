/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PAPER_TRADING_BANNER_TEXT } from '../constants';
import { StockViewHeader } from './StockViewHeader';

const confirmAppMock = vi.fn();
vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
}));

describe('StockViewHeader', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    confirmAppMock.mockReset();
    confirmAppMock.mockResolvedValue(false);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function renderHeader(overrides: Partial<Parameters<typeof StockViewHeader>[0]> = {}) {
    act(() => {
      root.render(
        <div className="stock-view-page">
          <StockViewHeader
            symbol="CJMB"
            detailReady
            detailSymbol="CJMB"
            mainPrice={1.47}
            mainChangeAbs={0.61}
            mainChangePct={70.73}
            isPositive
            refreshing={false}
            mode="paper"
            connected
            onLookup={() => {}}
            {...overrides}
          />
        </div>,
      );
    });
  }

  it('keeps symbol + clock; does not duplicate Paper/Live, Net Liq, BP, or operator modes', () => {
    renderHeader();
    const header = container.querySelector('[data-testid="stock-view-header"]');
    expect(header).toBeTruthy();
    expect(
      header!.querySelector('[data-testid="stock-view-market-clock"]'),
    ).toBeTruthy();
    expect(header!.textContent).toMatch(/ ET/);
    expect(header!.querySelector('[data-testid="stock-view-symbol-chip"]')).toBeTruthy();
    expect(header!.textContent).not.toMatch(/Net Liq/);
    expect(header!.textContent).not.toMatch(/\bBP\b/);
    expect(header!.querySelector('[data-testid="sv-account-mode-capsule"]')).toBeNull();
    expect(header!.querySelector('[data-testid="sv-operator-mode-capsule"]')).toBeNull();
    expect(header!.textContent).not.toMatch(/Fully Automated/);
    expect(header!.querySelector('[data-testid="sv-trading-lock"]')).toBeNull();
    expect(header!.textContent).not.toMatch(/Confirm|Auto Paper|Stop Automation|Hide charts|Show charts|✕ Close|← Back/);
  });

  it('hides Disconnected until IBKR status is known', () => {
    renderHeader({ connected: false, statusReady: false });
    expect(container.querySelector('[data-testid="sv-disconnect-warn"]')).toBeNull();
    renderHeader({ connected: false, statusReady: true });
    expect(container.querySelector('[data-testid="sv-disconnect-warn"]')?.textContent)
      .toMatch(/Disconnected/i);
  });

  it('shows paper trading banner only when mode is paper', () => {
    renderHeader({ mode: 'paper' });
    const banner = container.querySelector('[data-testid="paper-trading-banner"]');
    expect(banner).toBeTruthy();
    expect(banner!.textContent).toBe(PAPER_TRADING_BANNER_TEXT);

    renderHeader({ mode: 'live' });
    expect(container.querySelector('[data-testid="paper-trading-banner"]')).toBeNull();

    renderHeader({ mode: 'disconnected' });
    expect(container.querySelector('[data-testid="paper-trading-banner"]')).toBeNull();
  });
});
