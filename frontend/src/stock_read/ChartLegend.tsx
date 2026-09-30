/** The 1-minute pane's legend for the stock read: a chip per setup lane that switches its shapes on
 * and off, the "Past" chip for the day's setups that ended and the one for how much their labels say
 * (compact or full), the setups without a scanner (locked,
 * saying why), and -- after "show on chart" from the
 * decisions -- the moment in view with a way back to now. In the corner, the badge with the trade's
 * track and the Who trades chip under it, and the call (ENTER NOW, SELL NOW, what Nova did: ADR 037). */
import { tipProps, whyProps } from '../ux';
import { laneChip, planBadgeText } from './chartShapes';
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

/** Setups without a scanner the legend names: Gap and Go draws its level (the premarket high); the
 * parked micro pullback draws nothing, so it takes no room here (the sheet lists it). */
const LEGEND_NO_SCANNER = new Set(['gap_and_go']);

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
  const drawn = past.data ? drawnPast(past.data.episodes, layers.hidden) : [];
  const n = pastCounts(drawn);
  const words = past.data
    ? `Setups that ended today on ${ctx.symbol}: ${n.failed} failed (✕), ${n.faded} faded (○), ${n.triggered} triggered (✓),`
      + ' drawn faint where they happened. Hover a box for why it ended and what price did next.'
    : 'The day\'s setups that ended, drawn faint where they happened.';
  const trouble = [past.error, past.data?.journal.error, past.data?.bars.error].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={`sr-legend__chip sr-legend__chip--past${layers.past ? '' : ' sr-legend__chip--off'}`}
      aria-pressed={layers.past}
      onClick={() => ctx.setLayers({ past: !layers.past })}
      {...tipProps(`${words}${trouble ? ` ${trouble}` : ''} (click to ${layers.past ? 'hide' : 'show'} them)`, 'Past setups')}
      data-testid="stock-read-legend-past"
    >
      ◌ Past{past.data ? ` ${drawn.length}` : ''}
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

export function ChartLegend({ ctx, read, onFrame }: {
  ctx: StockReadContextValue;
  read: StockRead;
  /** Frame the forming setup on the pane. */
  onFrame: () => void;
}) {
  const { layers } = ctx;
  const moment = ctx.who.moment;
  const badge = moment?.badge ?? (layers.setups ? planBadgeText(read) : null);
  const tone = moment?.tone ?? read.plan?.state ?? 'manual';
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
            <PastChip ctx={ctx} />
            <LabelsChip ctx={ctx} />
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
      {moment?.call && <CallBox call={moment.call} />}
      <div className="sr-legend__corner">
        {badge && (
          <button
            type="button"
            className={`sr-legend__badge sr-legend__badge--${tone}`}
            onClick={onFrame}
            {...tipProps('Frame the setup on the chart', read.plan?.reason ?? null)}
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
