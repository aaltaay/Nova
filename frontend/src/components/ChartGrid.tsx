/** 2×2 multi-timeframe chart grid for the full trading/detail page. */
import { TickerChart, type ChartTradeUpdate } from '../TickerChart';
import { CHART_GRID_PANELS } from '../constants';

interface Props {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
}

export function ChartGrid({ symbol, lastTrade }: Props) {
  return (
    <div className="chart-grid" role="region" aria-label="Multi-timeframe charts">
      {CHART_GRID_PANELS.map(panel => (
        <div key={panel.id} className="chart-grid-cell">
          <TickerChart
            symbol={symbol}
            lastTrade={lastTrade}
            variant="grid"
            fixedTimeframe={panel.id}
            title={panel.label}
            subtitle={panel.note}
          />
        </div>
      ))}
    </div>
  );
}
