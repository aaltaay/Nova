/** The 1-minute pane's legend for the stock read: a chip per setup lane that switches its shapes on
 * and off, the setups without a scanner (locked, saying why), the plan's badge, and -- after "show on
 * chart" from the decisions -- the moment in view with a way back to now. */
import { tipProps, whyProps } from '../ux';
import { laneChip, planBadgeText } from './chartShapes';
import { hhmmssEt } from './timeWords';
import type { StockReadContextValue } from './StockReadContext';
import type { StockRead } from './types';
import './stockRead.css';
import './stockReadSheet.css';

function stop(e: { stopPropagation: () => void }): void {
  e.stopPropagation(); // a click here is not a chart gesture
}

/** Setups without a scanner the legend names: Gap and Go draws its level (the premarket high); the
 * parked micro pullback draws nothing, so it takes no room here (the sheet lists it). */
const LEGEND_NO_SCANNER = new Set(['gap_and_go']);

export function ChartLegend({ ctx, read, onFrame }: {
  ctx: StockReadContextValue;
  read: StockRead;
  /** Frame the forming setup on the pane. */
  onFrame: () => void;
}) {
  const { layers } = ctx;
  const badge = layers.setups ? planBadgeText(read) : null;
  const focus = ctx.focus;
  return (
    <div className="sr-legend" data-testid="stock-read-legend" onPointerDown={stop} onDoubleClick={stop}>
      <div className="sr-legend__chips">
        {!layers.setups ? (
          <button
            type="button"
            className="sr-legend__chip"
            onClick={() => ctx.setLayers({ setups: true })}
            data-testid="stock-read-legend-show"
          >
            ◆ Setups hidden · show
          </button>
        ) : (
          <>
            {read.setups.map(lane => {
              const chip = laneChip(lane);
              const off = layers.hidden.includes(lane.setup_type);
              return (
                <button
                  key={lane.setup_type}
                  type="button"
                  className={`sr-legend__chip sr-legend__chip--${chip.state}${off ? ' sr-legend__chip--off' : ''}`}
                  aria-pressed={!off}
                  onClick={() => ctx.toggleLane(lane.setup_type)}
                  {...tipProps(`${lane.reason || lane.state}${off ? ' (drawing hidden: click to show)' : ' (click to hide its drawing)'}`)}
                  data-testid={`stock-read-legend-${lane.setup_type}`}
                >
                  <i className="sr-legend__dot" aria-hidden="true" />
                  {chip.text}
                </button>
              );
            })}
            {read.no_scanner.filter(ns => LEGEND_NO_SCANNER.has(ns.setup_type)).map(ns => (
              <button
                key={ns.setup_type}
                type="button"
                className="sr-legend__chip sr-legend__chip--none"
                disabled
                {...whyProps(true, ns.reason)}
                data-testid={`stock-read-legend-${ns.setup_type}`}
              >
                <i className="sr-legend__dot" aria-hidden="true" />
                {ns.label}
              </button>
            ))}
          </>
        )}
      </div>
      {focus && (
        <div className="sr-legend__focus" data-testid="stock-read-focus">
          <span>⌖ {hhmmssEt(focus.ts)} {focus.event?.title ?? ''}</span>
          <button type="button" className="sr-link" onClick={ctx.clearFocus} data-testid="stock-read-focus-clear">
            Back to now
          </button>
        </div>
      )}
      {badge && (
        <button
          type="button"
          className={`sr-legend__badge sr-legend__badge--${read.plan?.state ?? 'manual'}`}
          onClick={onFrame}
          {...tipProps('Frame the setup on the chart', read.plan?.reason ?? null)}
          data-testid="stock-read-badge"
        >
          {badge}
        </button>
      )}
    </div>
  );
}
