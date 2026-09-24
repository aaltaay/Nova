/**
 * Close Position is one code path, not three (#116).
 *
 * Every UI that can flatten -- the Positions table, the chart Long/Short tag
 * menu, and the chart right-click menu -- renders the same
 * `ClosePositionButton` and must reach `closeFullPosition` with identical
 * arguments. A new entry point that hand-rolls its own place/flatten call will
 * fail here.
 *
 * @vitest-environment jsdom
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, type RefObject } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { ChartContextMenuHost } from '../chart/ChartContextMenuHost';
import { ChartPositionTag } from '../chart/ChartPositionTag';
import * as closeMod from '../ibkr/closeFullPosition';
import { PositionsPanel } from '../ibkr/PositionsPanel';
import type { IbkrPosition } from '../ibkr/types';

const SMPL: IbkrPosition = {
  symbol: 'SMPL',
  qty: 200,
  market_price: 4.25,
  market_value: 850,
  avg_cost: 3.1,
  unrealized_pnl: 230,
  realized_pnl: 0,
};

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

const status = vi.hoisted(() => ({ spend_status: 'paper_armed' }));

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: status.spend_status,
  }),
}));

// Armed, and disarmed: a disarmed desk can always get flat (ADR 018), so no
// entry point may add a padlock of its own.
const SPEND_STATUSES = ['paper_armed', 'locked_disarmed'];

vi.mock('../ibkr/IbkrAccountContext', () => ({
  useOptionalIbkrAccountContext: () => ({
    positions: [SMPL],
    stale: false,
    error: null,
  }),
}));

const EXPECTED_CALL = [
  'SMPL',
  200,
  expect.objectContaining({ referencePrice: 4.25 }),
];

describe('Close Position SSOT across every UI entry point', () => {
  let mount: HTMLDivElement;
  let root: Root;
  let spy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    status.spend_status = 'paper_armed';
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
    spy = vi.spyOn(closeMod, 'closeFullPosition').mockResolvedValue({
      ok: true,
      order_id: 7,
      side: 'SELL',
      qty: 200,
      outside_rth: false,
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
    vi.restoreAllMocks();
  });

  async function clickClose(testId: string) {
    const btn = document.querySelector(`[data-testid="${testId}"]`) as HTMLButtonElement;
    expect(btn, `missing ${testId}`).toBeTruthy();
    await act(async () => {
      btn.click();
    });
  }

  it.each(SPEND_STATUSES)('Positions table row flattens through closeFullPosition (%s)', async (spendStatus) => {
    act(() => {
      root.render(
        <PositionsPanel
          summary={null}
          positions={[SMPL]}
          orders={[]}
          selectedSymbol="SMPL"
          onSelectSymbol={() => {}}
          onOpenTrading={() => {}}
          mode="paper"
          connected
          spendStatus={spendStatus}
          compact
        />,
      );
    });
    await clickClose('close-position-btn');
    expect(spy).toHaveBeenCalledWith(...EXPECTED_CALL);
  });

  it.each(SPEND_STATUSES)('chart Long/Short tag menu flattens through closeFullPosition (%s)', async (spendStatus) => {
    act(() => {
      root.render(
        <ChartPositionTag
          position={SMPL}
          placement={{ top: 24, right: 8 }}
          mode="paper"
          connected
          spendStatus={spendStatus}
        />,
      );
    });
    act(() => {
      (document.querySelector(
        '[data-testid="chart-position-tag-btn"]',
      ) as HTMLButtonElement).dispatchEvent(
        new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0 }),
      );
    });
    await clickClose('chart-position-menu-close');
    expect(spy).toHaveBeenCalledWith(...EXPECTED_CALL);
  });

  it.each(SPEND_STATUSES)('chart right-click menu flattens through closeFullPosition (%s)', async (spendStatus) => {
    status.spend_status = spendStatus;
    const body = document.createElement('div');
    body.className = 'chart-body';
    document.body.appendChild(body);
    const containerRef = { current: body } as RefObject<HTMLElement | null>;
    const candleSeriesRef = {
      current: { coordinateToPrice: () => 4.25 } as unknown as ISeriesApi<'Candlestick'>,
    };
    act(() => {
      root.render(
        <ChartContextMenuHost
          symbol="SMPL"
          timeframe="1Day"
          barCount={40}
          chart={{} as IChartApi}
          candleSeriesRef={candleSeriesRef}
          containerRef={containerRef}
          activeTool={null}
          onToolClick={() => {}}
          enabledIndicators={['emas', 'vwap']}
          onIndicatorToggle={() => {}}
        />,
      );
    });
    act(() => {
      body.dispatchEvent(
        new MouseEvent('contextmenu', {
          bubbles: true,
          cancelable: true,
          clientX: 120,
          clientY: 90,
          button: 2,
        }),
      );
    });
    await clickClose('chart-context-menu-close-position');
    expect(spy).toHaveBeenCalledWith(...EXPECTED_CALL);
    body.remove();
  });

  it('no chart module reaches the broker on its own', () => {
    const chartDir = join(process.cwd(), 'src', 'chart');
    const offenders = readdirSync(chartDir)
      .filter((name) => /\.tsx?$/.test(name) && !name.includes('.test.'))
      .filter((name) => {
        const src = readFileSync(join(chartDir, name), 'utf8');
        return (
          src.includes("from '../ibkr/placeOrder'") ||
          src.includes("from '../ibkr/closeFullPosition'")
        );
      });
    expect(
      offenders,
      'chart code must stage the ticket / render ClosePositionButton, not place or flatten itself',
    ).toEqual([]);
  });
});
