/**
 * The other traders' shares on a chart (ADR 072): a dashed line in each trader's colour (OWNER_COLORS) at its
 * average -- Claude's, the brain's, a retired bot's -- priced on the axis like your own line, its words at the pane's
 * left. Describe-only: it opens no menu and stages nothing, and the chart's Flatten stays yours
 * (`useChartPositionContext`). Shares handed to you are on your own line.
 *
 * Its own component so the account poll that moves the words re-renders them, never the pane around them.
 */
import { useEffect, type CSSProperties, type RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { OWNER_COLORS, OWNER_NAMES, ownerBotName, type Owner } from '../constantGroups/owners';
import { othersRowsFor, useDeskPositions, type DeskPosition } from '../ibkr';
import { traderPositionLineOptions, traderPositionLineTitle } from './positionOverlay';
import { CHART_TRADER_WORDS_ROOM_PX } from './positionOverlayConstants';
import { useChartPositionTagLayout } from './useChartPositionTagLayout';
import './chartPositionTag.css';

interface PaneProps {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  barsRevision: number;
}

const traderName = (owner: Owner, bot: string | null | undefined): string =>
  (owner === 'earlier_bots' ? ownerBotName(bot) : OWNER_NAMES[owner]);

function TraderLine({ row, owner, chart, candleSeriesRef, containerRef, barsRevision }:
  PaneProps & { row: DeskPosition; owner: Owner }) {
  const avgCost = row.avg_cost ?? 0;
  // Keyed on the price and colour it draws, never on the poll: `useChartPositionOverlay` says what redrawing cost.
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chart || !series) return;
    const line = series.createPriceLine(traderPositionLineOptions(avgCost, owner));
    return () => {
      try {
        series.removePriceLine(line);
      } catch {
        /* chart already disposed */
      }
    };
  }, [chart, candleSeriesRef, avgCost, owner]);
  const placement = useChartPositionTagLayout({ chart, candleSeriesRef, containerRef, avgCost, barsRevision });
  if (placement.offScale) return null;
  const words = traderPositionLineTitle(traderName(owner, row.bot), {
    symbol: row.symbol, qty: row.qty, avgCost, unrealizedPnl: row.unrealized_pnl,
  });
  const under = placement.top < CHART_TRADER_WORDS_ROOM_PX;
  return (
    <div
      className={`chart-trader-position${under ? ' is-under' : ''}`}
      style={{ top: placement.top, '--chart-trader': OWNER_COLORS[owner] } as CSSProperties}
      data-testid="chart-trader-position"
      data-owner={owner}
    >
      {words}
    </div>
  );
}

export function ChartTradersPositions({ symbol, ...pane }: PaneProps & { symbol: string }) {
  const { rows } = useDeskPositions();
  return (
    <>
      {othersRowsFor(rows, symbol).map((row) => (row.owner ? (
        <TraderLine key={`${row.symbol}-${row.owner}-${row.bot ?? ''}`} row={row} owner={row.owner} {...pane} />
      ) : null))}
    </>
  );
}
