/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { LineStyle, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OWNER_COLORS } from '../constantGroups/owners';
import type { DeskPosition } from '../ibkr';
import { ChartTradersPositions } from './ChartTradersPositions';

const desk = vi.hoisted(() => ({ rows: [] as DeskPosition[] }));
const placement = vi.hoisted(() => ({ top: 40, right: 8, offScale: false }));

vi.mock('../ibkr', () => ({
  useDeskPositions: () => ({ rows: desk.rows }),
  othersRowsFor: (rows: DeskPosition[], symbol: string) =>
    rows.filter((r) => r.owner && r.owner !== 'you' && r.symbol === symbol),
}));
vi.mock('./useChartPositionTagLayout', () => ({ useChartPositionTagLayout: () => placement }));

const held = (symbol: string, qty: number, owner: DeskPosition['owner'], bot: string | null = null, avg_cost = 125.9): DeskPosition => ({
  symbol, qty, avg_cost, market_price: 124.89, market_value: qty * 124.89, unrealized_pnl: 19.19, realized_pnl: null,
  owner, bot,
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

describe('ChartTradersPositions (ADR 072)', () => {
  it("draws a dashed line in the trader's colour at its average, and says whose", () => {
    desk.rows = [held('ORCL', -19, 'claude')];
    const { series, props } = pane();
    render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledWith(expect.objectContaining({
      price: 125.9, color: OWNER_COLORS.claude, lineStyle: LineStyle.Dashed, axisLabelVisible: true,
    }));
    const words = screen.getByTestId('chart-trader-position');
    expect(words.textContent).toBe('Claude short 19 @ $125.90  +$19.19');
    expect(words.getAttribute('data-owner')).toBe('claude');
  });

  it('names a retired bot by its name, in Earlier bots\' grey', () => {
    desk.rows = [held('ORCL', -19, 'earlier_bots', 'live_trader')];
    const { series, props } = pane();
    render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledWith(expect.objectContaining({ color: OWNER_COLORS.earlier_bots }));
    expect(screen.getByTestId('chart-trader-position').textContent).toBe('Live Trader short 19 @ $125.90  +$19.19');
  });

  it("offers nothing to press: the chart's Flatten stays yours", () => {
    desk.rows = [held('ORCL', -19, 'claude')];
    const { props } = pane();
    const { container } = render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(container.querySelector('button')).toBeNull();
  });

  it("draws nothing for another stock's shares, or for yours", () => {
    desk.rows = [held('INTC', 40, 'brain'), held('ORCL', 100, 'you')];
    const { series, props } = pane();
    render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).not.toHaveBeenCalled();
    expect(screen.queryByTestId('chart-trader-position')).toBeNull();
  });

  it('gives each trader in the stock its own line, in its own colour', () => {
    desk.rows = [held('ORCL', -19, 'claude'), held('ORCL', 30, 'brain', null, 126.4)];
    const { series, props } = pane();
    render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine.mock.calls.map(([o]) => (o as { color: string }).color))
      .toEqual([OWNER_COLORS.claude, OWNER_COLORS.brain]);
    expect(screen.getAllByTestId('chart-trader-position')).toHaveLength(2);
  });

  it('takes its line off with it, and redraws only when the average moves', () => {
    desk.rows = [held('ORCL', -19, 'claude')];
    const { series, props } = pane();
    const view = render(<ChartTradersPositions symbol="ORCL" {...props} />);
    desk.rows = [{ ...held('ORCL', -19, 'claude'), unrealized_pnl: 25 }];
    view.rerender(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledTimes(1);
    desk.rows = [];
    view.rerender(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.removePriceLine).toHaveBeenCalledTimes(1);
  });

  it('puts the words under the line when the pane has no room over it', () => {
    desk.rows = [held('ORCL', -19, 'claude')];
    const { props } = pane();
    const view = render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(screen.getByTestId('chart-trader-position').className).toBe('chart-trader-position');
    placement.top = 9;
    view.rerender(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(screen.getByTestId('chart-trader-position').className).toBe('chart-trader-position is-under');
  });

  it('hides the words while the average is off the scale; the axis keeps the price', () => {
    desk.rows = [held('ORCL', -19, 'claude')];
    placement.offScale = true;
    const { series, props } = pane();
    render(<ChartTradersPositions symbol="ORCL" {...props} />);
    expect(series.createPriceLine).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('chart-trader-position')).toBeNull();
  });
});
