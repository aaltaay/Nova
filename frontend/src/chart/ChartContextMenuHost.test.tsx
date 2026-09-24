/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, createRef, type RefObject } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import * as closeMod from '../ibkr/closeFullPosition';
import * as prefillMod from '../ibkr/orderTicketPrefill';
import type { IbkrPosition } from '../ibkr/types';
import { ChartContextMenuHost } from './ChartContextMenuHost';
import { CHART_CONTEXT_MENU_TICKET_WAIT_REASON } from './chartContextMenuConstants';
import { getWatchList } from '../watch_list';
import { resetWatchListForTests } from '../watch_list/watchListStore';
import * as dockNav from '../stock_view/requestDockSurface';

const SMPL: IbkrPosition = {
  symbol: 'SMPL',
  qty: 200,
  market_price: 4.25,
  market_value: 850,
  avg_cost: 3.1,
  unrealized_pnl: 230,
  realized_pnl: 0,
};

let positions: IbkrPosition[] = [];

vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({
    symbols: [],
    isAllowed: () => false,
    add: vi.fn(),
    remove: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'paper_armed',
  }),
}));

vi.mock('../ibkr/IbkrAccountContext', () => ({
  useOptionalIbkrAccountContext: () => ({
    positions,
    stale: false,
    error: null,
  }),
}));

vi.mock('../ux', () => ({
  confirmApp: async () => true,
  alertApp: async () => undefined,
}));

vi.mock('../ibkr/useTradingPinGate', () => ({
  useTradingPinGate: () => ({ ensureUnlocked: async () => true, pinDialog: null }),
}));

vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
}));

describe('ChartContextMenuHost', () => {
  let mount: HTMLDivElement;
  let body: HTMLDivElement;
  let root: Root;
  let containerRef: RefObject<HTMLElement | null>;
  let candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  let onToolClick: ReturnType<typeof vi.fn>;
  let onIndicatorToggle: ReturnType<typeof vi.fn>;
  let chart: IChartApi;
  let applyOptions: ReturnType<typeof vi.fn>;
  let fitContent: ReturnType<typeof vi.fn>;
  let takeScreenshot: ReturnType<typeof vi.fn>;
  let ticketOff: (() => void) | null;

  /** Stand-in for the Trader's mounted ticket: the prefills it hears. */
  function mountTicket() {
    const heard = vi.fn();
    act(() => {
      ticketOff = prefillMod.subscribeOrderTicketPrefill('SMPL', heard);
    });
    return heard;
  }

  beforeEach(() => {
    ticketOff = null;
    positions = [];
    mount = document.createElement('div');
    document.body.appendChild(mount);
    // Stand-in for `.chart-body`: the host binds `contextmenu` here.
    body = document.createElement('div');
    body.className = 'chart-body';
    document.body.appendChild(body);
    containerRef = createRef<HTMLElement>() as RefObject<HTMLElement | null>;
    containerRef.current = body;
    candleSeriesRef = {
      current: { coordinateToPrice: () => 4.253 } as unknown as ISeriesApi<'Candlestick'>,
    };
    onToolClick = vi.fn();
    onIndicatorToggle = vi.fn();
    applyOptions = vi.fn();
    fitContent = vi.fn();
    takeScreenshot = vi.fn(() => ({
      toDataURL: () => 'data:image/png;base64,AAA',
    }) as unknown as HTMLCanvasElement);
    chart = {
      priceScale: () => ({ applyOptions }),
      timeScale: () => ({ setVisibleLogicalRange: vi.fn(), fitContent }),
      takeScreenshot,
    } as unknown as IChartApi;
    root = createRoot(mount);
  });

  afterEach(() => {
    ticketOff?.();
    act(() => root.unmount());
    mount.remove();
    body.remove();
    vi.restoreAllMocks();
  });

  function render(activeTool: string | null = null) {
    act(() => {
      root.render(
        <ChartContextMenuHost
          symbol="SMPL"
          timeframe="1Day"
          barCount={40}
          chart={chart}
          candleSeriesRef={candleSeriesRef}
          containerRef={containerRef}
          activeTool={activeTool}
          onToolClick={onToolClick}
          enabledIndicators={['emas', 'vwap']}
          onIndicatorToggle={onIndicatorToggle}
        />,
      );
    });
  }

  function rightClick(): MouseEvent {
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 240,
      clientY: 180,
      button: 2,
    });
    act(() => {
      body.dispatchEvent(event);
    });
    return event;
  }

  const menu = () => document.querySelector('[data-testid="chart-context-menu"]');
  const item = (id: string) =>
    document.querySelector(`[data-testid="chart-context-menu-${id}"]`) as HTMLButtonElement;

  it('opens at the cursor and suppresses the browser menu', () => {
    render();
    expect(menu()).toBeNull();
    const event = rightClick();
    expect(event.defaultPrevented).toBe(true);
    const node = menu() as HTMLElement;
    expect(node).toBeTruthy();
    expect(node.style.top).toBe('180px');
    expect(node.style.left).toBe('240px');
  });

  it('labels Webull order rows with the price under the cursor', () => {
    render();
    rightClick();
    expect(item('create_order').textContent).toBe('Create New Order @4.25');
    expect(item('buy').textContent).toMatch(/^Buy SMPL \d+ @4\.25$/);
    expect(item('sell').textContent).toMatch(/^Sell SMPL \d+ @4\.25$/);
  });

  it('ignores right-clicks on the Long/Short tag, which owns its own menu', () => {
    render();
    const tag = document.createElement('div');
    tag.className = 'chart-position-tag';
    body.appendChild(tag);
    act(() => {
      tag.dispatchEvent(
        new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 2 }),
      );
    });
    expect(menu()).toBeNull();
  });

  it('dismisses on Escape and on an outside pointerdown', () => {
    render();
    rightClick();
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(menu()).toBeNull();

    rightClick();
    act(() => {
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
    });
    expect(menu()).toBeNull();
  });

  it('Escape does not fall through to the drawing-tool / maximize handler', () => {
    const chartEscape = vi.fn();
    window.addEventListener('keydown', chartEscape);
    render();
    rightClick();
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(chartEscape).not.toHaveBeenCalled();
    window.removeEventListener('keydown', chartEscape);
  });

  it('Buy stages the trade ticket instead of placing an order', () => {
    const prefill = vi.spyOn(prefillMod, 'requestOrderTicketPrefill');
    const heard = mountTicket();
    render();
    rightClick();
    act(() => item('buy').click());
    expect(prefill).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'SMPL',
        side: 'BUY',
        orderType: 'LMT',
        limitPrice: '4.25',
      }),
    );
    expect(heard).toHaveBeenCalledWith(expect.objectContaining({ side: 'BUY', limitPrice: '4.25' }));
    expect(menu()).toBeNull();
  });

  it('Sell stages a SELL ticket at the same price', () => {
    const prefill = vi.spyOn(prefillMod, 'requestOrderTicketPrefill');
    mountTicket();
    render();
    rightClick();
    act(() => item('sell').click());
    expect(prefill).toHaveBeenCalledWith(
      expect.objectContaining({ side: 'SELL', limitPrice: '4.25' }),
    );
  });

  it('locks the priced rows with a reason until a ticket is listening, then stages it (#566)', () => {
    const prefill = vi.spyOn(prefillMod, 'requestOrderTicketPrefill');
    render();
    rightClick();
    for (const id of ['create_order', 'buy', 'sell']) {
      expect(item(id).disabled).toBe(true);
      expect(item(id).getAttribute('aria-disabled')).toBe('true');
      expect(item(id).getAttribute('data-why')).toBe(CHART_CONTEXT_MENU_TICKET_WAIT_REASON);
    }
    expect(item('buy').textContent).toMatch(/^Buy SMPL \d+ @4\.25$/);
    expect(document.querySelector('[data-testid="chart-context-menu-hint"]')?.textContent)
      .toBe(CHART_CONTEXT_MENU_TICKET_WAIT_REASON);
    act(() => item('buy').click());
    expect(prefill).not.toHaveBeenCalled();
    expect(menu()).toBeTruthy();

    // The quote lands and the Trader mounts its ticket while the menu is open.
    const heard = mountTicket();
    expect(item('buy').disabled).toBe(false);
    expect(item('buy').hasAttribute('data-why')).toBe(false);
    expect(document.querySelector('[data-testid="chart-context-menu-hint"]')?.textContent)
      .toContain('trade ticket');
    act(() => item('sell').click());
    expect(heard).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: 'SMPL', side: 'SELL', limitPrice: '4.25' }),
    );
    expect(menu()).toBeNull();
  });

  it('keeps the rows locked while only another symbol has a ticket', () => {
    act(() => {
      ticketOff = prefillMod.subscribeOrderTicketPrefill('AAPL', vi.fn());
    });
    render();
    rightClick();
    expect(item('buy').disabled).toBe(true);
    expect(item('sell').getAttribute('data-why')).toBe(CHART_CONTEXT_MENU_TICKET_WAIT_REASON);
  });

  it('Close Position appears only with an open position and uses the flatten SSOT', async () => {
    render();
    rightClick();
    expect(document.querySelector('[data-testid="chart-context-menu-close-position"]'))
      .toBeNull();

    positions = [SMPL];
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    render();
    rightClick();
    const close = document.querySelector(
      '[data-testid="chart-context-menu-close-position"]',
    ) as HTMLButtonElement;
    expect(close).toBeTruthy();
    expect(close.textContent).toBe('Close Position');

    const spy = vi.spyOn(closeMod, 'closeFullPosition').mockResolvedValue({
      ok: true,
      order_id: 11,
      side: 'SELL',
      qty: 200,
      outside_rth: false,
    });
    await act(async () => {
      close.click();
    });
    expect(spy).toHaveBeenCalledWith(
      'SMPL',
      200,
      expect.objectContaining({ referencePrice: 4.25 }),
    );
  });

  it('Drawings submenu arms an existing draw tool', () => {
    render();
    rightClick();
    act(() => item('drawings').click());
    const submenu = document.querySelector(
      '[data-testid="chart-context-menu-drawings-submenu"]',
    );
    expect(submenu).toBeTruthy();
    act(() => {
      (document.querySelector(
        '[data-testid="chart-context-menu-tool-TrendLine"]',
      ) as HTMLButtonElement).click();
    });
    expect(onToolClick).toHaveBeenCalledWith('TrendLine');
    expect(menu()).toBeNull();
  });

  it('marks the armed tool in the submenu', () => {
    render('HorizontalLine');
    rightClick();
    act(() => item('drawings').click());
    const armed = document.querySelector(
      '[data-testid="chart-context-menu-tool-HorizontalLine"]',
    ) as HTMLButtonElement;
    expect(armed.getAttribute('aria-checked')).toBe('true');
  });

  it('Reset Chart restores the pane scales', () => {
    render();
    rightClick();
    act(() => item('reset').click());
    expect(applyOptions).toHaveBeenCalledWith({ autoScale: true });
    expect(fitContent).toHaveBeenCalled();
  });

  it('Snapshot captures the pane through Lightweight Charts', () => {
    const realClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function noop() {};
    render();
    rightClick();
    act(() => item('snapshot').click());
    expect(takeScreenshot).toHaveBeenCalled();
    HTMLAnchorElement.prototype.click = realClick;
  });

  it('drops order rows when the series cannot price the cursor', () => {
    candleSeriesRef.current = {
      coordinateToPrice: () => null,
    } as unknown as ISeriesApi<'Candlestick'>;
    render();
    rightClick();
    expect(item('buy')).toBeNull();
    expect(item('reset')).toBeTruthy();
  });

  it('disables Create Alert with a visible reason', () => {
    render();
    rightClick();
    const alert = item('create_alert');
    expect(alert.disabled).toBe(true);
    expect(alert.textContent).toContain('No price alerts in Nova');
    act(() => alert.click());
    expect(menu()).toBeTruthy();
  });

  it('Add to watch list puts the symbol on the watch list and the next menu offers Remove', () => {
    localStorage.clear();
    resetWatchListForTests();
    render();
    rightClick();
    act(() => item('watch_list_add').click());
    expect(menu()).toBeNull();
    expect(getWatchList()).toContain('SMPL');
    rightClick();
    act(() => item('watch_list_remove').click());
    expect(getWatchList()).not.toContain('SMPL');
    localStorage.clear();
    resetWatchListForTests();
  });

  it('Show Layers toggles an existing indicator without dismissing', () => {
    render();
    rightClick();
    act(() => item('show_layers').click());
    expect(document.querySelector('[data-testid="chart-context-menu-layers-submenu"]'))
      .toBeTruthy();
    act(() => item('layer-vwap').click());
    expect(onIndicatorToggle).toHaveBeenCalledWith('vwap');
    expect(menu()).toBeTruthy();
  });

  it('View Trade Details docks Positions through the tag SSOT', () => {
    const spy = vi.spyOn(dockNav, 'requestStockViewDock');
    positions = [SMPL];
    render();
    rightClick();
    act(() => item('view_details').click());
    expect(spy).toHaveBeenCalledWith({ surface: 'positions' });
    expect(menu()).toBeNull();
  });
});
