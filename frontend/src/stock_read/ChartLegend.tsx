/** The 1-minute pane's legend for the stock read: a chip per setup lane that switches its shapes on
 * and off, the "Past" chip for the day's setups that ended and the one for how much their labels say
 * (compact or full), the setups without a scanner (locked,
 * saying why), and -- after "show on chart" from the
 * decisions -- the moment in view with a way back to now. In the corner, the badge with the trade's
 * track and the Who trades chip under it, and the call (ENTER NOW, SELL NOW, what Nova did: ADR 037). The
 * legend ends where the price axis begins, and it says how far down the corner reaches: the words at the
 * pane's right edge start under it. */
import { useEffect, useRef, type RefObject } from 'react';
import { liquidityTip } from '../setups';
import { tipProps, whyProps } from '../ux';
import { laneChip, planBadgeText } from './chartShapes';
import { ChartKey } from './ChartKey';
import { fiveMinuteOnMinute } from './fiveMinuteShapes';
import { chartKey } from './paneKeyRows';
import { CallBox, MomentTrack } from './MomentTrack';
import { drawnPast, pastCounts } from './pastSetups';
import { hhmmssEt } from './timeWords';
import { WhoTradesChip } from './WhoTradesChip';
import type { StockReadContextValue } from './StockReadContext';
import type { StockRead } from './types';
import './stockRead.css';
import './stockReadSheet.css';

function stop(e: { stopPropagation: () => void }): void {
  e.stopPropagation(); // a click here is not a chart gesture
}

/** The switch for the day's setups that ended, counting what it draws (ADR 036 amendment). */
function PastChip({ ctx }: { ctx: StockReadContextValue }) {
  const { past, layers } = ctx;
  if (past.unavailable) {
    return (
      <button type="button" className="sr-legend__chip sr-legend__chip--past" disabled data-testid="stock-read-legend-past"
        {...whyProps(true, 'This backend does not keep past setups yet: restart it on the newer code to see them')}>
        ◌ Past
      </button>
    );
  }
  // What the charts draw: this desk's read, never one from after a replay's playhead (#815).
  const data = ctx.pastNow ?? null;
  const drawn = data ? drawnPast(data.episodes, layers.hidden) : [];
  const n = pastCounts(drawn);
  const when = data?.replay ? 'by the playhead' : 'today';
  const words = data
    ? `Setups that ended ${when} on ${ctx.symbol}: ${n.failed} failed (✕), ${n.faded} faded (○), ${n.triggered} triggered (✓),`
      + ' drawn faint where they happened. Hover a box for why it ended and what price did next.'
    : 'The day\'s setups that ended, drawn faint where they happened.';
  const trouble = [past.error, data?.journal.error, data?.bars.error].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={`sr-legend__chip sr-legend__chip--past${layers.past ? '' : ' sr-legend__chip--off'}`}
      aria-pressed={layers.past}
      onClick={() => ctx.setLayers({ past: !layers.past })}
      {...tipProps(`${words}${trouble ? ` ${trouble}` : ''} (click to ${layers.past ? 'hide' : 'show'} them)`, 'Past setups')}
      data-testid="stock-read-legend-past"
    >
      ◌ Past{data ? ` ${drawn.length}` : ''}
    </button>
  );
}

const LABEL_WORDS = {
  compact: 'Compact: a mark for each -- ✕ failed, ○ faded, ✓ triggered. Point at a mark or its box for the whole story.',
  full: 'Full: the whole label (✕ topping tail · ↘ then broke down).',
} as const;

/** How much the past setups' labels say (operator report 2026-09-30: "extremely too crowded"): a mark
 * each, or the whole label. Either way a label that would run into another shrinks or steps aside. */
function LabelsChip({ ctx }: { ctx: StockReadContextValue }) {
  const { layers } = ctx;
  if (!layers.past || ctx.past.unavailable) return null;
  const next = layers.labels === 'full' ? 'compact' : 'full';
  const words = layers.labels === 'full'
    ? `${LABEL_WORDS.full} Where two would touch, the older one shrinks to a few words, then its mark, or steps aside;`
      + ` point at any box for its whole story. (click for ${next})`
    : `${LABEL_WORDS.compact} Where two marks would touch, the older one steps aside. (click for ${next})`;
  return (
    <button
      type="button"
      className="sr-legend__chip sr-legend__chip--past"
      aria-pressed={layers.labels === 'full'}
      onClick={() => ctx.setLayers({ labels: next })}
      {...tipProps(words, 'Past setup labels')}
      data-testid="stock-read-legend-labels"
    >
      {layers.labels === 'full' ? '¶ Full' : '¶ Compact'}
    </button>
  );
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

export function ChartLegend({ ctx, read, onFrame, right = null, containerRef, onCornerBottom }: {
  ctx: StockReadContextValue;
  read: StockRead;
  /** Frame the forming setup on the pane. */
  onFrame: () => void;
  /** The legend's right edge from the pane's (the price axis's width); null keeps the stylesheet's. */
  right?: number | null;
  containerRef?: RefObject<HTMLElement | null>;
  /** How far below the pane's top the corner chips reach, in pixels. */
  onCornerBottom?: (px: number) => void;
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
        <ChartKey sections={chartKey('full', layers)} testId="stock-read-key-full" />
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
            {read.setups.map(lane => {
              const chip = laneChip(lane);
              const off = layers.hidden.includes(lane.setup_type);
              // A strategy at Off on the Bots page draws nothing: the chip says so and cannot turn it back on here.
              const strategyOff = lane.level === 0;
              return (
                <button
                  key={lane.setup_type}
                  type="button"
                  className={`sr-legend__chip sr-legend__chip--${chip.state}${off ? ' sr-legend__chip--off' : ''}`}
                  aria-pressed={!off}
                  disabled={strategyOff}
                  onClick={() => ctx.toggleLane(lane.setup_type)}
                  {...(strategyOff
                    ? whyProps(true, 'This strategy is Off on the Bots page: Nova draws nothing for it. Set it to Eyes or On there.')
                    : tipProps(`${lane.reason || lane.state}${off ? ' (drawing hidden: click to show)' : ' (click to hide its drawing)'}`))}
                  data-testid={`stock-read-legend-${lane.setup_type}`}
                >
                  <i className="sr-legend__dot" aria-hidden="true" />
                  {chip.text}
                </button>
              );
            })}
            <PastChip ctx={ctx} />
            <LabelsChip ctx={ctx} />
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
