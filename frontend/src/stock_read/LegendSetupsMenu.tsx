/** The 1-minute legend's Setups menu (operator 2026-10-12, of fifteen chips over the candles: "this is too
 * much"). The legend keeps a chip only for a setup doing something (`onLegendRow`); this menu holds every
 * setup with its switch and where it stands, longs and shorts side by side, then the day's setups that ended
 * and how much their labels say. It opens under the legend's chips and stays open while switches are
 * flipped; a press outside it or Escape closes it. */
import { useEffect, useRef, useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { laneChip } from './chartShapes';
import { drawnPast, pastCounts } from './pastSetups';
import type { StockReadContextValue } from './StockReadContext';
import type { SetupLane } from './types';

const STRATEGY_OFF_WHY = 'This strategy is Off on Strategy Bots: Nova draws nothing for it. Set it to Eyes or On there.';

/** A lane earns a chip on the legend's row while it is doing something, or is the plan's: shown, not hidden,
 * and its strategy not Off. */
export function onLegendRow(lane: SetupLane, hidden: string[]): boolean {
  if (lane.level === 0 || hidden.includes(lane.setup_type)) return false;
  return lane.chosen || laneChip(lane).state !== 'idle';
}

function LaneRow({ ctx, lane }: { ctx: StockReadContextValue; lane: SetupLane }) {
  const chip = laneChip(lane);
  const off = ctx.layers.hidden.includes(lane.setup_type);
  // A strategy at Off on the Bots page draws nothing (ADR 044): hidden though the operator did not hide it, the
  // row says so and cannot turn it back on here.
  const strategyOff = lane.level === 0 || (off && !ctx.prefs.hidden.includes(lane.setup_type));
  return (
    <button
      type="button"
      className={`sr-menu__row sr-legend__chip--${chip.state}${off || strategyOff ? ' sr-menu__row--off' : ''}`}
      aria-pressed={!off && !strategyOff}
      disabled={strategyOff}
      onClick={() => ctx.toggleLane(lane.setup_type)}
      {...(strategyOff
        ? whyProps(true, STRATEGY_OFF_WHY)
        : tipProps(`${lane.reason || lane.state}${off ? ' (drawing hidden: click to show)' : ' (click to hide its drawing)'}`))}
      data-testid={`stock-read-menu-${lane.setup_type}`}
    >
      <i className="sr-menu__tick" aria-hidden="true">{!off && !strategyOff ? '✓' : ''}</i>
      <i className="sr-legend__dot" aria-hidden="true" />
      <span className="sr-menu__name">{chip.name.replace(/^▼ /, '')}</span>
      <span className="sr-menu__word">{strategyOff ? 'Off' : chip.word}</span>
    </button>
  );
}

const LABEL_WORDS = {
  compact: 'Compact: a mark for each -- ✕ failed, ○ faded, ✓ triggered. Point at a mark or its box for the whole story.'
    + ' Where two marks would touch, the older one steps aside.',
  full: 'Full: the whole label (✕ topping tail · ↘ then broke down). Where two would touch, the older one shrinks to a'
    + ' few words, then its mark, or steps aside; point at any box for its whole story.',
} as const;

/** The switch for the day's setups that ended, counting what it draws (ADR 036 amendment), and how much their
 * labels say (operator report 2026-09-30: "extremely too crowded"). */
function PastRow({ ctx }: { ctx: StockReadContextValue }) {
  const { past, layers } = ctx;
  if (past.unavailable) {
    return (
      <div className="sr-menu__past">
        <button type="button" className="sr-menu__row sr-menu__row--off" disabled data-testid="stock-read-legend-past"
          {...whyProps(true, 'This backend does not keep past setups yet: restart it on the newer code to see them')}>
          <i className="sr-menu__tick" aria-hidden="true" />
          <span className="sr-menu__name">◌ Past setups</span>
        </button>
      </div>
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
    <div className="sr-menu__past">
      <button
        type="button"
        className={`sr-menu__row${layers.past ? '' : ' sr-menu__row--off'}`}
        aria-pressed={layers.past}
        onClick={() => ctx.setLayers({ past: !layers.past })}
        {...tipProps(`${words}${trouble ? ` ${trouble}` : ''} (click to ${layers.past ? 'hide' : 'show'} them)`, 'Past setups')}
        data-testid="stock-read-legend-past"
      >
        <i className="sr-menu__tick" aria-hidden="true">{layers.past ? '✓' : ''}</i>
        <span className="sr-menu__name">◌ Past setups{data ? ` (${drawn.length})` : ''}</span>
      </button>
      {layers.past && (
        <span className="sr-menu__seg" role="group" aria-label="Past setup labels" data-testid="stock-read-legend-labels">
          {(['compact', 'full'] as const).map(v => (
            <button
              key={v}
              type="button"
              aria-pressed={layers.labels === v}
              onClick={() => ctx.setLayers({ labels: v })}
              {...tipProps(LABEL_WORDS[v], 'Past setup labels')}
              data-testid={`stock-read-legend-labels-${v}`}
            >
              {v === 'compact' ? '¶ Compact' : 'Full'}
            </button>
          ))}
        </span>
      )}
    </div>
  );
}

export function LegendSetupsMenu({ ctx, lanes }: { ctx: StockReadContextValue; lanes: SetupLane[] }) {
  const [open, setOpen] = useState(false);
  const chipRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const inside = (t: EventTarget | null) => t instanceof Node && (chipRef.current?.contains(t) || cardRef.current?.contains(t));
    // Capture: the legend stops its own presses from reaching the chart, and so from reaching the document.
    const onDown = (e: PointerEvent) => { if (!inside(e.target)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('pointerdown', onDown, true);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointerdown', onDown, true);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);
  const more = lanes.filter(l => !onLegendRow(l, ctx.layers.hidden)).length;
  const longs = lanes.filter(l => l.side !== 'short');
  const shorts = lanes.filter(l => l.side === 'short');
  return (
    <>
      <button
        ref={chipRef}
        type="button"
        className="sr-legend__chip sr-legend__chip--menu"
        aria-expanded={open}
        aria-haspopup="true"
        // A press must not focus the chip: focus would bring its tip back up over the menu it just opened.
        onMouseDown={e => e.preventDefault()}
        onClick={() => setOpen(o => !o)}
        {...(open ? {} : tipProps(`Every setup with its switch, and the day's setups that ended.${more
          ? ` ${more} not shown as a chip: idle, hidden or Off. A setup that starts forming gets its chip back on its own.`
          : ''}`, 'Setups'))}
        data-testid="stock-read-legend-menu"
      >
        Setups ▾{more ? <b>+{more}</b> : null}
      </button>
      {open && (
        <div className="sr-menu" ref={cardRef} role="group" aria-label="Setups" data-testid="stock-read-legend-menu-card">
          <div className={`sr-menu__cols${shorts.length ? '' : ' sr-menu__cols--one'}`}>
            <div>
              <div className="sr-menu__title">{shorts.length ? 'LONG' : 'SETUPS'}</div>
              {longs.map(l => <LaneRow key={l.setup_type} ctx={ctx} lane={l} />)}
            </div>
            {shorts.length > 0 && (
              <div>
                <div className="sr-menu__title">SHORT ▼</div>
                {shorts.map(l => <LaneRow key={l.setup_type} ctx={ctx} lane={l} />)}
              </div>
            )}
          </div>
          <div className="sr-menu__sep" />
          <PastRow ctx={ctx} />
        </div>
      )}
    </>
  );
}
