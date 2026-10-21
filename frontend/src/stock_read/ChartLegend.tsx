/** The 1-minute pane's legend for the stock read: a chip for each setup lane doing something, which
 * switches its shapes on and off, and the Setups menu holding every lane's switch, the day's setups that
 * ended and how much their labels say (`LegendSetupsMenu`); after "show on chart" from the
 * decisions -- the moment in view with a way back to now. In the corner, the badge with the trade's
 * track and the Who trades chip under it, and the call (ENTER NOW, SELL NOW, what Nova did: ADR 037). The
 * legend ends where the price axis begins, and it says how far down the corner reaches: the words at the
 * pane's right edge start under it. */
import { useEffect, useRef, type RefObject } from 'react';
import { liquidityTip } from '../setups';
import { tipProps } from '../ux';
import { laneChip, planBadgeText } from './chartShapes';
import { ChartKey } from './ChartKey';
import { fiveMinuteOnMinute } from './fiveMinuteShapes';
import { LegendSetupsMenu, onLegendRow } from './LegendSetupsMenu';
import { chartKey, type KeySection } from './paneKeyRows';
import { CallBox, MomentTrack } from './MomentTrack';
import { hhmmssEt } from './timeWords';
import { WhoTradesChip } from './WhoTradesChip';
import type { StockReadContextValue } from './StockReadContext';
import type { StockRead } from './types';
import './stockRead.css';
import './stockReadSheet.css';

function stop(e: { stopPropagation: () => void }): void {
  e.stopPropagation(); // a click here is not a chart gesture
}

/** Calls `report` with how far below `containerRef`'s top `corner` reaches, whenever that changes. */
function useCornerBottom(corner: RefObject<HTMLDivElement | null>, containerRef: RefObject<HTMLElement | null> | undefined,
  report: ((px: number) => void) | undefined): void {
  useEffect(() => {
    const el = corner.current;
    if (!el || !report) return;
    const measure = () => {
      const box = containerRef?.current;
      const r = el.getBoundingClientRect();
      report(r.height > 0 && box ? Math.max(0, Math.round(r.bottom - box.getBoundingClientRect().top)) : 0);
    };
    measure();
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    ro?.observe(el);
    return () => {
      ro?.disconnect();
      report(0);
    };
  }, [corner, containerRef, report]);
}

export function ChartLegend({ ctx, read, onFrame, right = null, containerRef, onCornerBottom, extraKey = [] }: {
  ctx: StockReadContextValue;
  read: StockRead;
  /** Frame the forming setup on the pane. */
  onFrame: () => void;
  /** The legend's right edge from the pane's (the price axis's width); null keeps the stylesheet's. */
  right?: number | null;
  containerRef?: RefObject<HTMLElement | null>;
  /** How far below the pane's top the corner chips reach, in pixels. */
  onCornerBottom?: (px: number) => void;
  /** Sections other layers on the pane add to its Key, listed first (Ahead's zone while it is on). */
  extraKey?: KeySection[];
}) {
  const corner = useRef<HTMLDivElement>(null);
  useCornerBottom(corner, containerRef, onCornerBottom);
  const { layers } = ctx;
  const eyes = ctx.prefs.eyes;
  // Eyes off (ADR 044): no badge, except a call about shares you hold (the trade's moment is Holding or past it).
  const moment = eyes || (ctx.who.moment?.step ?? 0) >= 2 ? ctx.who.moment : null;
  const badge = moment?.badge ?? (layers.setups ? planBadgeText(read) : null);
  const tone = moment?.tone ?? read.plan?.state ?? 'manual';
  const focus = ctx.focus;
  return (
    <div className="sr-legend" data-testid="stock-read-legend" onPointerDown={stop} onDoubleClick={stop}
      style={right === null ? undefined : { right }}>
      <div className="sr-legend__chips">
        <ChartKey sections={[...extraKey, ...chartKey('full', layers)]} testId="stock-read-key-full" />
        {!eyes ? (
          <button
            type="button"
            className="sr-legend__chip"
            onClick={() => ctx.setLayers({ eyes: true })}
            {...tipProps('Eyes is off: Nova draws nothing on this tab. Click to turn it back on.')}
            data-testid="stock-read-legend-show"
          >
            👁 Eyes off · show
          </button>
        ) : !layers.setups ? (
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
            {/* Only a lane doing something has a chip; the Setups menu holds every lane's switch (operator
                2026-10-12: fifteen chips over the candles were "too much"). Hiding one moves it to the menu. */}
            {read.setups.filter(lane => onLegendRow(lane, layers.hidden)).map(lane => {
              const chip = laneChip(lane);
              return (
                <button
                  key={lane.setup_type}
                  type="button"
                  className={`sr-legend__chip sr-legend__chip--${chip.state}`}
                  aria-pressed
                  onClick={() => ctx.toggleLane(lane.setup_type)}
                  {...tipProps(`${lane.reason || lane.state} (click to hide its drawing; the Setups menu shows it again)`)}
                  data-testid={`stock-read-legend-${lane.setup_type}`}
                >
                  <i className="sr-legend__dot" aria-hidden="true" />
                  {chip.text}
                </button>
              );
            })}
            {fiveMinuteOnMinute(read).chips.map(c => (
              <span
                key={`5m-${c.setupType}`}
                className="sr-legend__chip sr-legend__chip--live sr-legend__chip--five"
                {...tipProps(c.tip, '5-minute setup')}
                data-testid={`stock-read-legend-5m-${c.setupType}`}
              >
                <i className="sr-legend__dot" aria-hidden="true" />
                {c.text}
              </span>
            ))}
            <LegendSetupsMenu ctx={ctx} lanes={read.setups} />
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
      {moment?.call && <CallBox call={moment.call} />}
      <div className="sr-legend__corner" ref={corner}>
        {badge && (
          <button
            type="button"
            className={`sr-legend__badge sr-legend__badge--${tone}`}
            onClick={onFrame}
            {...(tone === 'thin' && read.plan?.liquidity
              ? tipProps(`${liquidityTip(read.plan.liquidity)}\nClick to frame the setup on the chart.`, 'Too thin to trade')
              : tipProps('Frame the setup on the chart', read.plan?.reason ?? null))}
            data-testid="stock-read-badge"
          >
            {badge}
          </button>
        )}
        {moment?.track && <MomentTrack moment={moment} />}
        <WhoTradesChip ctx={ctx} />
      </div>
    </div>
  );
}
