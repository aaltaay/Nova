/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { LineStyle, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DeskPosition } from '../ibkr';
import { ChartBotsPositions } from './ChartBotsPositions';
import { CHART_POSITION_BOTS_COLOR } from './positionOverlayConstants';

const desk = vi.hoisted(() => ({ rows: [] as DeskPosition[] }));
const placement = vi.hoisted(() => ({ top: 40, right: 8, offScale: false }));

vi.mock('../ibkr', () => ({
  useDeskPositions: () => ({ rows: desk.rows }),
  botsRowsFor: (rows: DeskPosition[], symbol: string) => rows.filter((r) => r.owner === 'bots' && r.symbol === symbol),
}));
vi.mock('./useChartPositionTagLayout', () => ({ useChartPositionTagLayout: () => placement }));

const bots = (symbol: string, qty: number, bot: string, avg_cost = 125.9): DeskPosition => ({
  symbol, qty, avg_cost, market_price: 124.89, market_value: qty * 124.89, unrealized_pnl: 19.19, realized_pnl: null,
  owner: 'bots', bot,
});

function pane() {
  const series = { createPriceLine: vi.fn((options: object) => options), removePriceLine: vi.fn() };
  const props = {
    chart: {} as IChartApi,
    candleSeriesRef: { current: series as unknown as ISeriesApi<'Candlestick'> },
    containerRef: { current: document.createElement('div') },
    barsRevision: 1,
  };
  return { series, props };
}

beforeEach(() => {
  desk.rows = [];
  placement.top = 40;
  placement.offScale = false;
});
afterEach(cleanup);

describe('ChartBotsPositions (ADR 069 decision 9)', () => {
  it("draws a dashed line in the bots' colour at their average, and says whose", () => {
    desk.rows = [bots('ORCL', -19, 'live_trader')];
    const { series, props } = pane();
    render(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledWith(expect.objectContaining({
      price: 125.9, color: CHART_POSITION_BOTS_COLOR, lineStyle: LineStyle.Dashed, axisLabelVisible: true,
    }));
    expect(screen.getByTestId('chart-bots-position').textContent).toBe('Live Trader short 19 @ $125.90  +$19.19');
  });

  it('offers nothing to press: the chart\'s Flatten stays yours', () => {
    desk.rows = [bots('ORCL', -19, 'live_trader')];
    const { props } = pane();
    const { container } = render(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(container.querySelector('button')).toBeNull();
  });

  it("draws nothing for another stock's shares", () => {
    desk.rows = [bots('INTC', 40, 'live_trader')];
    const { series, props } = pane();
    render(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).not.toHaveBeenCalled();
    expect(screen.queryByTestId('chart-bots-position')).toBeNull();
  });

  it('gives each bot in the stock its own line', () => {
    desk.rows = [bots('ORCL', -19, 'live_trader'), bots('ORCL', -5, 'claude', 126.4)];
    const { series, props } = pane();
    render(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledTimes(2);
    expect(screen.getAllByTestId('chart-bots-position')).toHaveLength(2);
  });

  it('takes its line off with it, and redraws only when the average moves', () => {
    desk.rows = [bots('ORCL', -19, 'live_trader')];
    const { series, props } = pane();
    const view = render(<ChartBotsPositions symbol="ORCL" {...props} />);
    desk.rows = [{ ...bots('ORCL', -19, 'live_trader'), unrealized_pnl: 25 }];
    view.rerender(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledTimes(1);
    desk.rows = [];
    view.rerender(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(series.removePriceLine).toHaveBeenCalledTimes(1);
  });

  it('puts the words under the line when the pane has no room over it', () => {
    desk.rows = [bots('ORCL', -19, 'live_trader')];
    const { props } = pane();
    const view = render(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(screen.getByTestId('chart-bots-position').className).toBe('chart-bots-position');
    placement.top = 9;
    view.rerender(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(screen.getByTestId('chart-bots-position').className).toBe('chart-bots-position is-under');
  });

  it('hides the words while the average is off the scale; the axis keeps the price', () => {
    desk.rows = [bots('ORCL', -19, 'live_trader')];
    placement.offScale = true;
    const { series, props } = pane();
    render(<ChartBotsPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('chart-bots-position')).toBeNull();
  });
});
