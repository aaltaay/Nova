/**
 * The bots' shares on a chart (ADR 069 decision 9): a dashed line in the bots' colour at each bot's average, priced
 * on the axis like your own line, its words at the pane's left. Describe-only: it opens no menu and stages nothing,
 * and the chart's Flatten stays yours (`useChartPositionContext`).
 *
 * Its own component so the account poll that moves the words re-renders them, never the pane around them.
 */
import { useEffect, type RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { ownerBotName } from '../constantGroups/owners';
import { botsRowsFor, useDeskPositions, type DeskPosition } from '../ibkr';
import { botsPositionLineOptions, botsPositionLineTitle } from './positionOverlay';
import { CHART_BOTS_WORDS_ROOM_PX } from './positionOverlayConstants';
import { useChartPositionTagLayout } from './useChartPositionTagLayout';
import './chartPositionTag.css';

interface PaneProps {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  barsRevision: number;
}

function BotsLine({ row, chart, candleSeriesRef, containerRef, barsRevision }: PaneProps & { row: DeskPosition }) {
  const avgCost = row.avg_cost ?? 0;
  // Keyed on the price it draws, never on the poll: `useChartPositionOverlay` says what redrawing cost.
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chart || !series) return;
    const line = series.createPriceLine(botsPositionLineOptions(avgCost));
    return () => {
      try {
        series.removePriceLine(line);
      } catch {
        /* chart already disposed */
      }
    };
  }, [chart, candleSeriesRef, avgCost]);
  const placement = useChartPositionTagLayout({ chart, candleSeriesRef, containerRef, avgCost, barsRevision });
  if (placement.offScale) return null;
  const words = botsPositionLineTitle(ownerBotName(row.bot), {
    symbol: row.symbol, qty: row.qty, avgCost, unrealizedPnl: row.unrealized_pnl,
  });
  const under = placement.top < CHART_BOTS_WORDS_ROOM_PX;
  return (
    <div
      className={`chart-bots-position${under ? ' is-under' : ''}`}
      style={{ top: placement.top }}
      data-testid="chart-bots-position"
    >
      {words}
    </div>
  );
}

export function ChartBotsPositions({ symbol, ...pane }: PaneProps & { symbol: string }) {
  const { rows } = useDeskPositions();
  return (
    <>
      {botsRowsFor(rows, symbol).map((row) => (
        <BotsLine key={`${row.symbol}-${row.bot ?? ''}`} row={row} {...pane} />
      ))}
    </>
  );
}
