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
        {...tipProps('The high of day, the premarket high, the open and the half dollars either side of the price; a level off the chart gets a tag at its edge.', 'Levels')}
        data-testid="stock-read-toggle-levels"
      >
        Levels: HOD · PMH · open · ½$ {layers.levels ? '' : '(off)'}
      </button>
    </span>
  );
}
