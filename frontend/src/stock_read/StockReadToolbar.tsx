/**
 * The chart toolbar's Eyes switch (ADR 044): everything Nova draws on every pane of the tab -- the
 * setups forming and ended, the plan's lines, zones and badge, support and resistance -- on or off in
 * one click, with Setups and Levels as its two parts. Remembered with the other layers; your
 * indicators, your drawings, your orders and the Who trades switch never turn off with it.
 */
import { tipProps, whyProps } from '../ux';
import { useStockReadContext } from './StockReadContext';
import './stockRead.css';
import './stockReadSheet.css';

const EYES_TIP = 'Everything Nova draws on this tab\'s charts: the setups forming and the ones that ended, the plan\'s '
  + 'entry, stop and target with their zones and badge, and support and resistance. Off leaves your candles, '
  + 'volume, VWAP, EMAs, RSI, MACD, your own drawings and your orders. A call about shares you hold still shows.';
const SETUPS_TIP = 'The setups forming on the 1-minute chart and the ones that ended today, and the plan\'s entry, '
  + 'stop and target on every intraday chart.';
const LEVELS_TIP = 'Support and resistance, on the chart each comes from: today\'s map on the 5-minute, the daily '
  + 'levels on the Full Day chart, and on the 1-minute the high of day, the nearest round numbers and the levels '
  + 'between your stop and target. Hover a label or an axis tick for what holds it and what the data says.';
const PARTS_OFF_WHY = 'Eyes is off: turn it on to choose its parts.';

export function StockReadToolbar() {
  const ctx = useStockReadContext();
  if (!ctx) return null;
  const { prefs } = ctx;
  const eyes = prefs.eyes;
  return (
    <span className={`sr-toolbar sr-eyes${eyes ? ' sr-eyes--on' : ''}`} data-testid="stock-read-toolbar">
      <button
        type="button"
        className="chart-grid__optional-toggle sr-toolbar__btn sr-eyes__main"
        aria-pressed={eyes}
        onClick={() => ctx.setLayers({ eyes: !eyes })}
        {...tipProps(EYES_TIP, eyes ? 'Eyes on' : 'Eyes off')}
        data-testid="stock-read-toggle-eyes"
      >
        <span aria-hidden="true">👁</span> Eyes {eyes ? 'on' : 'off'}
      </button>
      <button
        type="button"
        className="chart-grid__optional-toggle sr-toolbar__btn sr-eyes__part"
        aria-pressed={eyes && prefs.setups}
        disabled={!eyes}
        {...(eyes ? tipProps(SETUPS_TIP, 'Setups') : whyProps(true, PARTS_OFF_WHY))}
        onClick={() => ctx.setLayers({ setups: !prefs.setups })}
        data-testid="stock-read-toggle-setups"
      >
        {prefs.setups ? '✓ ' : ''}Setups
      </button>
      <button
        type="button"
        className="chart-grid__optional-toggle sr-toolbar__btn sr-eyes__part"
        aria-pressed={eyes && prefs.levels}
        disabled={!eyes}
        {...(eyes ? tipProps(LEVELS_TIP, 'Levels') : whyProps(true, PARTS_OFF_WHY))}
        onClick={() => ctx.setLayers({ levels: !prefs.levels })}
        data-testid="stock-read-toggle-levels"
      >
        {prefs.levels ? '✓ ' : ''}Levels
      </button>
    </span>
  );
}
