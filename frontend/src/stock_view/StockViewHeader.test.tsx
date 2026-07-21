/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  PAPER_TRADING_BANNER_TEXT,
  STOCK_VIEW_ACCOUNT_MODE_LIVE,
  STOCK_VIEW_ACCOUNT_MODE_PAPER,
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO,
  STOCK_VIEW_OPERATOR_MODE_MANUAL,
  STOCK_VIEW_OPERATOR_MODE_NORMAL,
} from '../constants';
import { StockViewHeader } from './StockViewHeader';

const confirmAppMock = vi.fn();
vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
}));

describe('StockViewHeader trading chrome', () => {
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
            summary={{
              connected: true,
              mode: 'paper',
              NetLiquidation: 584,
              BuyingPower: 578,
            }}
            onLookup={() => {}}
            {...overrides}
          />
        </div>,
      );
    });
  }

  it('shows Net Liq, BP, Paper/Live, mode capsule — not lock, automate, or Hide charts', () => {
    renderHeader();
    const header = container.querySelector('[data-testid="stock-view-header"]');
    expect(header).toBeTruthy();
    expect(
      header!.querySelector('[data-testid="stock-view-market-clock"]'),
    ).toBeTruthy();
    expect(header!.textContent).toMatch(/ ET/);
    expect(header!.textContent).toMatch(/Net Liq/);
    expect(header!.textContent).toMatch(/\$584/);
    expect(header!.textContent).toMatch(/BP/);
    expect(header!.textContent).toMatch(/\$578/);
    expect(header!.textContent).toMatch(new RegExp(STOCK_VIEW_ACCOUNT_MODE_PAPER));
    expect(header!.textContent).toMatch(new RegExp(STOCK_VIEW_ACCOUNT_MODE_LIVE));
    expect(header!.textContent).toMatch(new RegExp(STOCK_VIEW_OPERATOR_MODE_MANUAL));
    expect(header!.textContent).toMatch(new RegExp(STOCK_VIEW_OPERATOR_MODE_NORMAL));
    expect(header!.textContent).toMatch(new RegExp(STOCK_VIEW_OPERATOR_MODE_FULL_AUTO));
    expect(header!.querySelector('[data-testid="sv-trading-lock"]')).toBeNull();
    expect(header!.textContent).not.toMatch(/Confirm|Auto Paper|Stop Automation|Hide charts|Show charts|✕ Close|← Back/);
    expect(header!.querySelector('.ticker-trade-bar-automate')).toBeNull();
  });

  it('selects Normal and disables Manual + Fully Automated', () => {
    renderHeader();
    const capsule = container.querySelector('[data-testid="sv-operator-mode-capsule"]');
    expect(capsule).toBeTruthy();
    const segs = capsule!.querySelectorAll('.sv-capsule__seg');
    expect(segs.length).toBe(3);
    expect(segs[0].textContent).toBe(STOCK_VIEW_OPERATOR_MODE_MANUAL);
    expect(segs[0]).toHaveProperty('disabled', true);
    expect(segs[1].textContent).toBe(STOCK_VIEW_OPERATOR_MODE_NORMAL);
    expect(segs[1].classList.contains('is-selected')).toBe(true);
    expect((segs[1] as HTMLButtonElement).disabled).toBe(false);
    expect(segs[2].textContent).toBe(STOCK_VIEW_OPERATOR_MODE_FULL_AUTO);
    expect(segs[2]).toHaveProperty('disabled', true);
  });

  it('marks Paper selected for paper Gateway and does not arm Live on click', async () => {
    confirmAppMock.mockResolvedValue(false);
    renderHeader({ mode: 'paper' });
    const account = container.querySelector('[data-testid="sv-account-mode-capsule"]');
    const segs = account!.querySelectorAll('.sv-capsule__seg');
    expect(segs[0].classList.contains('is-selected')).toBe(true);
    expect(segs[0].classList.contains('is-paper')).toBe(true);
    expect(segs[1].classList.contains('is-selected')).toBe(false);
    await act(async () => {
      (segs[1] as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(confirmAppMock).toHaveBeenCalled();
    expect(segs[1].classList.contains('is-selected')).toBe(false);
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
