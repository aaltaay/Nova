/** The chart toolbar's two stock-read switches: the setups' drawings, and the day's levels. */
import { tipProps } from '../ux';
import { useStockReadContext } from './StockReadContext';
import './stockRead.css';
import './stockReadSheet.css';

export function StockReadToolbar() {
  const ctx = useStockReadContext();
  if (!ctx) return null;
  const { layers } = ctx;
  return (
    <span className="sr-toolbar" data-testid="stock-read-toolbar">
      <button
        type="button"
        className="chart-grid__optional-toggle sr-toolbar__btn"
        aria-pressed={layers.setups}
        onClick={() => ctx.setLayers({ setups: !layers.setups })}
        {...tipProps('The setups forming on the 1-minute chart, the plan\'s entry, stop and target on every intraday chart.', 'Setups')}
        data-testid="stock-read-toggle-setups"
      >
        ◆ Setups {layers.setups ? 'on' : 'off'}
      </button>
      <button
        type="button"
        className="chart-grid__optional-toggle sr-toolbar__btn"
        aria-pressed={layers.levels}
        onClick={() => ctx.setLayers({ levels: !layers.levels })}
        {...tipProps('Support and resistance, on the chart each comes from: today\'s map on the 5-minute, the daily levels on the Full Day chart, and on the 1-minute the high of day, the premarket high, the open, the nearest round number either side (half and whole dollars up to $25, coarser above) and the levels between your stop and target. Hover a label or an axis tick for what holds it and what the data says; a level off the chart gets a tag at its edge.', 'Levels')}
        data-testid="stock-read-toggle-levels"
      >
        Levels {layers.levels ? 'on' : 'off'}
      </button>
    </span>
  );
}
