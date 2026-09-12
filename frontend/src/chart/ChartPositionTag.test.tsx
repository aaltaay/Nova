/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import * as closeMod from '../ibkr/closeFullPosition';
import * as dockNav from '../stock_view/requestDockSurface';
import type { IbkrPosition } from '../ibkr/types';
import { ChartPositionTag } from './ChartPositionTag';
import {
  CHART_POSITION_MENU_CLOSE,
  CHART_POSITION_MENU_VIEW_DETAILS,
} from './positionOverlayConstants';

const confirmAppMock = vi.fn();
const alertAppMock = vi.fn();
const ensureUnlockedMock = vi.fn(async () => true);

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
  alertApp: (...args: unknown[]) => alertAppMock(...args),
}));

vi.mock('../ibkr/useTradingPinGate', () => ({
  useTradingPinGate: () => ({
    ensureUnlocked: (...args: unknown[]) => ensureUnlockedMock(...args),
    pinDialog: null,
  }),
}));

vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
}));

const SMPL: IbkrPosition = {
  symbol: 'SMPL',
  qty: 200,
  market_price: 4.25,
  market_value: 850,
  avg_cost: 3.1,
  unrealized_pnl: 230,
  realized_pnl: 0,
};

describe('ChartPositionTag', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    confirmAppMock.mockReset();
    alertAppMock.mockReset();
    ensureUnlockedMock.mockReset();
    ensureUnlockedMock.mockResolvedValue(true);
    confirmAppMock.mockResolvedValue(true);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
  });

  function renderTag() {
    act(() => {
      root.render(
        <ChartPositionTag
          position={SMPL}
          placement={{ top: 24, right: 8 }}
          mode="paper"
          connected
          spendStatus="paper_armed"
        />,
      );
    });
  }

  function openMenu() {
    const btn = container.querySelector(
      '[data-testid="chart-position-tag-btn"]',
    ) as HTMLButtonElement;
    act(() => {
      btn.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
    });
  }

  it('opens a Webull-style menu on left-click and keeps chart gestures from bubbling', () => {
    renderTag();
    const parent = document.createElement('div');
    parent.appendChild(container);
    let bubbled = false;
    parent.addEventListener('pointerdown', () => {
      bubbled = true;
    });
    const btn = container.querySelector(
      '[data-testid="chart-position-tag-btn"]',
    ) as HTMLButtonElement;
    expect(btn.textContent).toMatch(/Long 200/);
    act(() => {
      btn.dispatchEvent(
        new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0 }),
      );
    });
    expect(bubbled).toBe(false);
    expect(container.querySelector('[data-testid="chart-position-menu"]')).toBeTruthy();
    expect(container.textContent).toContain(CHART_POSITION_MENU_CLOSE);
    expect(container.textContent).toContain(CHART_POSITION_MENU_VIEW_DETAILS);
  });

  it('closes on Escape and on an outside pointerdown', () => {
    renderTag();
    openMenu();
    expect(container.querySelector('[data-testid="chart-position-menu"]')).toBeTruthy();
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(container.querySelector('[data-testid="chart-position-menu"]')).toBeNull();

    openMenu();
    act(() => {
      document.body.dispatchEvent(
        new MouseEvent('pointerdown', { bubbles: true, cancelable: true }),
      );
    });
    expect(container.querySelector('[data-testid="chart-position-menu"]')).toBeNull();
  });

  it('View Trade Details requests the Positions dock', () => {
    const spy = vi.spyOn(dockNav, 'requestStockViewDock');
    renderTag();
    openMenu();
    act(() => {
      (container.querySelector(
        '[data-testid="chart-position-menu-details"]',
      ) as HTMLButtonElement).click();
    });
    expect(spy).toHaveBeenCalledWith({ surface: 'positions' });
    expect(container.querySelector('[data-testid="chart-position-menu"]')).toBeNull();
  });

  it('Close Position uses the existing flatten path', async () => {
    const spy = vi.spyOn(closeMod, 'closeFullPosition').mockResolvedValue({
      ok: true,
      order_id: 9,
      side: 'SELL',
      qty: 200,
      outside_rth: false,
    });
    renderTag();
    openMenu();
    await act(async () => {
      (container.querySelector(
        '[data-testid="chart-position-menu-close"]',
      ) as HTMLButtonElement).click();
    });
    expect(spy).toHaveBeenCalledWith(
      'SMPL',
      200,
      expect.objectContaining({ referencePrice: 4.25 }),
    );
  });
});
